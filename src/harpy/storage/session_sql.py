"""Versioned TUI session adapter for migrated SQL roots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from harpy.storage.backend import BackendMarker, database_file
from harpy.storage.engine import create_sqlite_engine
from harpy.storage.schema import Review
from harpy.storage.workspace import ActorContext, TenantWorkspace, VersionConflict


@dataclass(frozen=True)
class SqlReviewSession:
    review_id: UUID
    statuses: dict[str, str]
    notes: dict[str, str]
    selected_id: str | None
    selected_file: str | None
    lens: str
    focused_pane: str
    search: str
    history: list[dict[str, object]]
    history_index: int
    review_progress: str


@dataclass
class SessionBaseline:
    statuses: dict[str, str]
    notes: dict[str, str]
    decision_versions: dict[str, int]
    note_versions: dict[str, int]
    report_id: UUID


_BASELINES: dict[tuple[str, str], SessionBaseline] = {}


def _cache_key(root: Path, review_id: UUID) -> tuple[str, str]:
    return (str(root.resolve()), str(review_id))


def _context(marker: BackendMarker) -> ActorContext:
    return ActorContext(
        tenant_id=marker.tenant_id,
        actor_id=marker.actor_id,
        role="administrator",
        correlation_id=uuid4(),
        authorization_version=1,
    )


def open_sql_session(root: Path, marker: BackendMarker) -> tuple[Engine, Session, TenantWorkspace]:
    engine = create_sqlite_engine(database_file(root, marker))
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    return engine, db, TenantWorkspace(db, _context(marker), artifact_root=root / "artifacts")


def _project(
    workspace: TenantWorkspace, review_id: UUID
) -> tuple[SqlReviewSession, SessionBaseline]:
    report_id = workspace.latest_report_id(review_id)
    if report_id is None:
        empty = SqlReviewSession(
            review_id=review_id,
            statuses={},
            notes={},
            selected_id=None,
            selected_file=None,
            lens="overview",
            focused_pane="navigator",
            search="",
            history=[],
            history_index=0,
            review_progress="",
        )
        return empty, SessionBaseline({}, {}, {}, {}, uuid4())
    mapping = workspace.change_ids_for(report_id)
    statuses: dict[str, str] = {}
    notes: dict[str, str] = {}
    decision_versions: dict[str, int] = {}
    note_versions: dict[str, int] = {}
    for local_id, change_id in mapping.items():
        decision = workspace.get_decision(report_id, change_id)
        statuses[local_id] = decision.status
        decision_versions[local_id] = decision.version
        note = workspace.get_note(report_id, change_id)
        if note.text:
            notes[local_id] = note.text
        note_versions[local_id] = note.version
    personal = workspace.get_personal_session(review_id, "tui")
    selection = personal.selection if personal is not None else {}
    raw_history = personal.history if personal is not None else []
    history = [item for item in raw_history if isinstance(item, dict)]
    progress = workspace.progress(report_id)
    index = selection.get("history_index")
    projected = SqlReviewSession(
        review_id=review_id,
        statuses=statuses,
        notes=notes,
        selected_id=str(selection["selected_id"]) if selection.get("selected_id") else None,
        selected_file=str(selection["selected_file"]) if selection.get("selected_file") else None,
        lens=str(selection.get("lens") or "overview"),
        focused_pane=str(selection.get("focused_pane") or "navigator"),
        search=str(selection.get("search") or ""),
        history=history,
        history_index=index if isinstance(index, int) else 0,
        review_progress=f"{progress.reviewed}/{progress.total}",
    )
    return projected, SessionBaseline(statuses, notes, decision_versions, note_versions, report_id)


def load_sql_session(
    review_id: UUID, *, root: Path, marker: BackendMarker
) -> SqlReviewSession | None:
    engine, db, workspace = open_sql_session(root, marker)
    try:
        if workspace.session.get(Review, (marker.tenant_id, review_id)) is None:
            return None
        session, baseline = _project(workspace, review_id)
        _BASELINES[_cache_key(root, review_id)] = baseline
        return session
    finally:
        db.close()
        engine.dispose()


def save_sql_session(session: SqlReviewSession, *, root: Path, marker: BackendMarker) -> None:
    engine, db, workspace = open_sql_session(root, marker)
    try:
        report_id = workspace.latest_report_id(session.review_id)
        if report_id is None:
            return
        mapping = workspace.change_ids_for(report_id)
        baseline = _BASELINES.get(_cache_key(root, session.review_id))
        for local_id, status in session.statuses.items():
            change_id = mapping.get(local_id)
            if change_id is None:
                continue
            decision = workspace.get_decision(report_id, change_id)
            if baseline is None:
                if decision.version != 0:
                    continue
                expected = 0
            elif baseline.statuses.get(local_id, "unreviewed") == status:
                continue
            else:
                expected = baseline.decision_versions.get(local_id, 0)
            try:
                workspace.set_decision(
                    report_id=report_id,
                    change_id=change_id,
                    status=status,
                    expected_version=expected,
                    idempotency_key=uuid4(),
                )
            except VersionConflict:
                continue
        for local_id, text in session.notes.items():
            change_id = mapping.get(local_id)
            if change_id is None:
                continue
            note = workspace.get_note(report_id, change_id)
            if baseline is None:
                if note.version != 0:
                    continue
                expected = 0
            elif baseline.notes.get(local_id, "") == text:
                continue
            else:
                expected = baseline.note_versions.get(local_id, 0)
            try:
                workspace.save_note(
                    report_id=report_id,
                    change_id=change_id,
                    text=text,
                    expected_version=expected,
                    idempotency_key=uuid4(),
                )
            except VersionConflict:
                continue
        workspace.save_personal_session(
            session.review_id,
            client_kind="tui",
            selection={
                "selected_id": session.selected_id,
                "selected_file": session.selected_file,
                "lens": session.lens,
                "focused_pane": session.focused_pane,
                "search": session.search,
                "history_index": session.history_index,
            },
            history=list(session.history),
            report_id=report_id,
        )
        db.commit()
        _, updated = _project(workspace, session.review_id)
        _BASELINES[_cache_key(root, session.review_id)] = updated
    finally:
        db.close()
        engine.dispose()
