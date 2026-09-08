"""File-backed durable store used when the interpreter has no _sqlite3."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from harpy.models import AnalysisReport, ReportProvenance
from harpy.storage.catalog import BrowserCatalog
from harpy.storage.files import write_bytes

APP_SCHEMA_VERSION = 1


class StorageError(RuntimeError):
    pass


class SchemaTooNewError(StorageError):
    pass


def _read_json(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"durable database is corrupt: {exc}") from exc
    if not isinstance(loaded, dict):
        raise StorageError("durable database is corrupt: expected object")
    return {str(key): value for key, value in loaded.items()}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


class ReviewStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "review.json"
        self.reports_dir = root / "reports"
        self.evidence_dir = root / "evidence"
        self.catalog = BrowserCatalog(root)
        root.mkdir(parents=True, exist_ok=True)
        if self.path.is_file():
            data = _read_json(self.path)
            raw_version = data.get("schema_version")
            version = 0
            if isinstance(raw_version, int):
                version = raw_version
            elif isinstance(raw_version, str) and raw_version.isdigit():
                version = int(raw_version)
            if version > APP_SCHEMA_VERSION:
                raise SchemaTooNewError(
                    f"database schema {version} is newer than application {APP_SCHEMA_VERSION}"
                )
            self.data = data
        else:
            backup = self.path.with_suffix(".json.bak")
            self.data = {
                "schema_version": APP_SCHEMA_VERSION,
                "reports": {},
                "notes": {},
                "decisions": {},
                "decision_events": [],
                "runs": {},
            }
            if backup.exists():
                pass
            _write_json(self.path, self.data)
            _write_json(backup, self.data)

    def close(self) -> None:
        _write_json(self.path, self.data)

    def _reload(self) -> None:
        if self.path.is_file():
            self.data = _read_json(self.path)

    def _save(self) -> None:
        _write_json(self.path, self.data)

    def put_report(self, report: AnalysisReport) -> None:
        self._reload()
        digest = write_bytes(self.reports_dir, report.model_dump_json().encode("utf-8"))
        reports = self._map("reports")
        reports[str(report.id)] = {
            "snapshot_id": str(report.snapshot_id),
            "file": digest,
            "schema_version": report.schema_version,
        }
        self._save()

    def get_report(self, report_id: UUID) -> AnalysisReport | None:
        reports = self._map("reports")
        item = reports.get(str(report_id))
        if not isinstance(item, dict):
            return None
        digest = str(item.get("file") or "")
        path = self.reports_dir / digest
        if not path.is_file():
            return None
        return AnalysisReport.model_validate_json(path.read_text(encoding="utf-8"))

    def has_report_row(self, report_id: UUID) -> bool:
        return str(report_id) in self._map("reports")

    def add_note(self, review_id: UUID, text: str) -> UUID:
        self._reload()
        note_id = uuid4()
        notes = self._map("notes")
        notes[str(note_id)] = {"review_id": str(review_id), "text": text}
        self._save()
        return note_id

    def notes_for(self, review_id: UUID) -> list[str]:
        notes = self._map("notes")
        found: list[str] = []
        for item in notes.values():
            if isinstance(item, dict) and item.get("review_id") == str(review_id):
                found.append(str(item.get("text") or ""))
        return found

    def record_decision(self, review_id: UUID, change_id: UUID, status: str, payload: str) -> None:
        self._reload()
        decisions = self._map("decisions")
        decisions[f"{review_id}:{change_id}"] = {
            "review_id": str(review_id),
            "change_id": str(change_id),
            "status": status,
            "payload": payload,
        }
        events = self.data.setdefault("decision_events", [])
        if isinstance(events, list):
            events.append(
                {"review_id": str(review_id), "change_id": str(change_id), "payload": payload}
            )
        self._save()

    def decision_count(self, review_id: UUID) -> int:
        self._reload()
        return sum(
            1
            for item in self._map("decisions").values()
            if isinstance(item, dict) and item.get("review_id") == str(review_id)
        )

    def event_count(self) -> int:
        self._reload()
        events = self.data.get("decision_events")
        return len(events) if isinstance(events, list) else 0

    def claim_run(self, snapshot_id: UUID, plan_digest: str, owner: str) -> UUID:
        self._reload()
        runs = self._map("runs")
        for raw in runs.values():
            if not isinstance(raw, dict):
                continue
            if (
                raw.get("snapshot_id") == str(snapshot_id)
                and raw.get("plan_digest") == plan_digest
                and raw.get("status") in {"queued", "running"}
            ):
                return UUID(str(raw["id"]))
        run_id = uuid4()
        runs[str(run_id)] = {
            "id": str(run_id),
            "snapshot_id": str(snapshot_id),
            "plan_digest": plan_digest,
            "owner": owner,
            "status": "running",
            "heartbeat": datetime.now(UTC).isoformat(),
        }
        self._save()
        return run_id

    def heartbeat(self, run_id: UUID, owner: str) -> None:
        runs = self._map("runs")
        item = runs.get(str(run_id))
        if isinstance(item, dict) and item.get("owner") == owner:
            item["heartbeat"] = datetime.now(UTC).isoformat()
            self._save()

    def interrupt_dead_run(self, run_id: UUID, *, stale_after: float = 30.0) -> bool:
        runs = self._map("runs")
        item = runs.get(str(run_id))
        if not isinstance(item, dict):
            return False
        beat = datetime.fromisoformat(str(item.get("heartbeat")))
        if (datetime.now(UTC) - beat).total_seconds() < stale_after:
            return False
        item["status"] = "partial"
        self._save()
        return True

    def put_empty_report(self, snapshot_id: UUID) -> AnalysisReport:
        report = AnalysisReport(
            id=uuid4(),
            snapshot_id=snapshot_id,
            provenance=ReportProvenance(run_id=uuid4()),
        )
        self.put_report(report)
        return report

    def _map(self, key: str) -> dict[str, object]:
        value = self.data.setdefault(key, {})
        if not isinstance(value, dict):
            raise StorageError("durable database is corrupt: expected object")
        return value

    @property
    def conn(self) -> ReviewStore:
        return self
