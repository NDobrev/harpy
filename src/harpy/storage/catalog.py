"""File-backed browser catalog and inbox cache, shared by store backends."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from harpy.models import AnalysisResult, BrowserItem, Freshness
from harpy.storage.files import write_bytes

CATALOG_NAME = "browser.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"entries": {}, "inbox": {}}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": {}, "inbox": {}}
    if not isinstance(loaded, dict):
        return {"entries": {}, "inbox": {}}
    return {str(key): value for key, value in loaded.items()}


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


class BrowserCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / CATALOG_NAME
        self.results_dir = root / "results"

    def put_entry(self, item: BrowserItem, result: AnalysisResult | None = None) -> BrowserItem:
        data = _read(self.path)
        entries = _as_map(data, "entries")
        key = _entry_key(item)
        existing = entries.get(key)
        if isinstance(existing, dict) and existing.get("review_id") and item.review_id is None:
            item = item.model_copy(update={"review_id": UUID(str(existing["review_id"]))})
        if result is not None:
            digest = write_bytes(self.results_dir, result.model_dump_json().encode("utf-8"))
            payload = item.model_dump(mode="json")
            payload["result_file"] = digest
            payload["has_local_report"] = True
        else:
            payload = item.model_dump(mode="json")
            if isinstance(existing, dict) and existing.get("result_file"):
                payload["result_file"] = existing["result_file"]
                payload["has_local_report"] = True
                if item.review_id is None and existing.get("review_id"):
                    payload["review_id"] = existing["review_id"]
        entries[key] = payload
        data["entries"] = entries
        _write(self.path, data)
        return BrowserItem.model_validate(payload)

    def list_entries(self) -> list[BrowserItem]:
        entries = _as_map(_read(self.path), "entries")
        items = [
            BrowserItem.model_validate(raw) for raw in entries.values() if isinstance(raw, dict)
        ]
        return sorted(items, key=lambda item: item.analyzed_at or item.updated_at, reverse=True)

    def get_entry(self, review_id: UUID) -> BrowserItem | None:
        for item in self.list_entries():
            if item.review_id == review_id:
                return item
        return None

    def get_result(self, review_id: UUID) -> AnalysisResult | None:
        entries = _as_map(_read(self.path), "entries")
        for raw in entries.values():
            if not isinstance(raw, dict) or str(raw.get("review_id")) != str(review_id):
                continue
            digest = str(raw.get("result_file") or "")
            path = self.results_dir / digest
            if not path.is_file():
                return None
            return AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
        return None

    def get_result_by_report(self, report_id: UUID) -> AnalysisResult | None:
        for item in self.list_entries():
            if item.report_id == report_id and item.review_id is not None:
                return self.get_result(item.review_id)
        return None

    def put_inbox(
        self, tab: str, rows: list[dict[str, object]], *, error: str = "", truncated: bool = False
    ) -> None:
        data = _read(self.path)
        inbox = _as_map(data, "inbox")
        inbox[tab] = {
            "fetched_at": _now(),
            "error": error,
            "truncated": truncated,
            "rows": rows,
        }
        data["inbox"] = inbox
        _write(self.path, data)

    def put_session(self, review_id: UUID, payload: dict[str, object]) -> None:
        data = _read(self.path)
        sessions = _as_map(data, "sessions")
        sessions[str(review_id)] = payload
        data["sessions"] = sessions
        _write(self.path, data)

    def get_session(self, review_id: UUID) -> dict[str, object] | None:
        sessions = _as_map(_read(self.path), "sessions")
        raw = sessions.get(str(review_id))
        return raw if isinstance(raw, dict) else None

    def get_inbox(self, tab: str) -> tuple[list[dict[str, object]], str, str, bool]:
        inbox = _as_map(_read(self.path), "inbox")
        raw = inbox.get(tab)
        if not isinstance(raw, dict):
            return [], "", "", False
        rows = raw.get("rows")
        items = [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
        return (
            items,
            str(raw.get("fetched_at") or ""),
            str(raw.get("error") or ""),
            bool(raw.get("truncated")),
        )


def _as_map(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.setdefault(key, {})
    if not isinstance(value, dict):
        return {}
    return value


def _entry_key(item: BrowserItem) -> str:
    if item.repo and item.number is not None:
        return f"{item.repo}#{item.number}"
    if item.review_id is not None:
        return str(item.review_id)
    return f"{item.source}:{item.title}"


def freshness_for(analyzed_rev: str, latest_rev: str) -> Freshness:
    if not analyzed_rev and not latest_rev:
        return Freshness.UNKNOWN
    if not latest_rev or not analyzed_rev:
        return Freshness.UNKNOWN
    if analyzed_rev.startswith(latest_rev) or latest_rev.startswith(analyzed_rev):
        return Freshness.CURRENT
    return Freshness.CODE_CHANGED
