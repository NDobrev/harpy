"""SQLite durable store used when _sqlite3 is available."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from harpy.models import AnalysisReport, ReportProvenance
from harpy.storage.files import write_bytes
from harpy.storage.paths import database_path

APP_SCHEMA_VERSION = 1
_BUSY_MS = 5000

_V1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT,
    status TEXT NOT NULL,
    owner TEXT NOT NULL,
    heartbeat TEXT NOT NULL,
    plan_digest TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_decisions (
    review_id TEXT NOT NULL,
    change_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (review_id, change_id)
);
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    review_id TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT NOT NULL,
    change_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS reports_snapshot ON reports(snapshot_id);
CREATE INDEX IF NOT EXISTS runs_status ON analysis_runs(status);
"""


class StorageError(RuntimeError):
    pass


class SchemaTooNewError(StorageError):
    pass


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(path), timeout=_BUSY_MS / 1000)
    except sqlite3.DatabaseError as exc:
        raise StorageError(f"durable database is corrupt: {exc}") from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={_BUSY_MS}")
        conn.execute("SELECT 1")
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise StorageError(f"durable database is corrupt: {exc}") from exc
    return conn


def _db_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if row is None:
        return 0
    version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    if version is None or version[0] is None:
        return 0
    return int(version[0])


def migrate(path: Path) -> sqlite3.Connection:
    conn = _connect(path)
    current = _db_version(conn)
    if current > APP_SCHEMA_VERSION:
        conn.close()
        raise SchemaTooNewError(
            f"database schema {current} is newer than application {APP_SCHEMA_VERSION}"
        )
    if current == APP_SCHEMA_VERSION:
        return conn
    conn.execute("BEGIN EXCLUSIVE")
    backup = path.with_suffix(path.suffix + ".bak")
    with sqlite3.connect(str(backup)) as dest:
        conn.backup(dest)
    conn.executescript(_V1)
    conn.execute(
        "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (APP_SCHEMA_VERSION, datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return conn


class ReviewStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = database_path(root)
        self.reports_dir = root / "reports"
        self.evidence_dir = root / "evidence"
        self.conn = migrate(self.path)

    def close(self) -> None:
        self.conn.close()

    def put_report(self, report: AnalysisReport) -> None:
        digest = write_bytes(self.reports_dir, report.model_dump_json().encode("utf-8"))
        payload = json.dumps({"file": digest, "schema_version": report.schema_version})
        self.conn.execute(
            "INSERT OR REPLACE INTO reports(id, snapshot_id, created_at, payload) VALUES (?,?,?,?)",
            (str(report.id), str(report.snapshot_id), datetime.now(UTC).isoformat(), payload),
        )
        self.conn.commit()

    def get_report(self, report_id: UUID) -> AnalysisReport | None:
        row = self.conn.execute(
            "SELECT payload FROM reports WHERE id = ?", (str(report_id),)
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        digest = str(payload.get("file") or "")
        path = self.reports_dir / digest
        if not path.is_file():
            return None
        return AnalysisReport.model_validate_json(path.read_text(encoding="utf-8"))

    def has_report_row(self, report_id: UUID) -> bool:
        row = self.conn.execute("SELECT id FROM reports WHERE id = ?", (str(report_id),)).fetchone()
        return row is not None

    def add_note(self, review_id: UUID, text: str) -> UUID:
        note_id = uuid4()
        self.conn.execute(
            "INSERT INTO notes(id, review_id, payload) VALUES (?,?,?)",
            (str(note_id), str(review_id), json.dumps({"text": text})),
        )
        self.conn.commit()
        return note_id

    def notes_for(self, review_id: UUID) -> list[str]:
        rows = self.conn.execute(
            "SELECT payload FROM notes WHERE review_id = ?", (str(review_id),)
        ).fetchall()
        return [str(json.loads(row["payload"]).get("text") or "") for row in rows]

    def record_decision(self, review_id: UUID, change_id: UUID, status: str, payload: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO review_decisions(review_id, change_id, status, payload) "
            "VALUES (?,?,?,?)",
            (str(review_id), str(change_id), status, payload),
        )
        self.conn.execute(
            "INSERT INTO decision_events(review_id, change_id, payload) VALUES (?,?,?)",
            (str(review_id), str(change_id), payload),
        )
        self.conn.commit()

    def decision_count(self, review_id: UUID) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM review_decisions WHERE review_id = ?", (str(review_id),)
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def event_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM decision_events").fetchone()
        return int(row[0]) if row is not None else 0

    def claim_run(self, snapshot_id: UUID, plan_digest: str, owner: str) -> UUID:
        now = datetime.now(UTC).isoformat()
        row = self.conn.execute(
            "SELECT id FROM analysis_runs "
            "WHERE snapshot_id = ? AND plan_digest = ? AND status IN ('queued','running')",
            (str(snapshot_id), plan_digest),
        ).fetchone()
        if row is not None:
            return UUID(str(row["id"]))
        run_id = uuid4()
        self.conn.execute(
            "INSERT INTO analysis_runs(id, snapshot_id, status, owner, heartbeat, plan_digest, payload) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(run_id), str(snapshot_id), "running", owner, now, plan_digest, "{}"),
        )
        self.conn.commit()
        return run_id

    def heartbeat(self, run_id: UUID, owner: str) -> None:
        self.conn.execute(
            "UPDATE analysis_runs SET heartbeat = ? WHERE id = ? AND owner = ?",
            (datetime.now(UTC).isoformat(), str(run_id), owner),
        )
        self.conn.commit()

    def interrupt_dead_run(self, run_id: UUID, *, stale_after: float = 30.0) -> bool:
        row = self.conn.execute(
            "SELECT heartbeat FROM analysis_runs WHERE id = ?", (str(run_id),)
        ).fetchone()
        if row is None:
            return False
        beat = datetime.fromisoformat(str(row["heartbeat"]))
        if (datetime.now(UTC) - beat).total_seconds() < stale_after:
            return False
        self.conn.execute(
            "UPDATE analysis_runs SET status = 'partial' WHERE id = ?", (str(run_id),)
        )
        self.conn.commit()
        return True

    def put_empty_report(self, snapshot_id: UUID) -> AnalysisReport:
        report = AnalysisReport(
            id=uuid4(),
            snapshot_id=snapshot_id,
            provenance=ReportProvenance(run_id=uuid4()),
        )
        self.put_report(report)
        return report
