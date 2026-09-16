from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from harpy.storage.engine import create_sqlite_engine, initialize_engine
from harpy.storage.migrate import upgrade_head
from harpy.storage.schema import Membership, Report
from harpy.storage.workspace import (
    AccessDenied,
    ActorContext,
    IdempotencyConflict,
    NotFound,
    TenantWorkspace,
    VersionConflict,
    create_local_graph,
    next_decision_status,
)


def _engine(tmp_path: Path) -> Engine:
    engine = create_sqlite_engine(tmp_path / "harpy.sqlite3")
    initialize_engine(engine)
    return engine


def _sessions(engine: Engine) -> Session:
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    return factory()


def test_alembic_upgrade_creates_decision_tables(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'migrated.sqlite3'}"
    upgrade_head(url)
    engine = create_sqlite_engine(tmp_path / "migrated.sqlite3")
    with engine.connect() as connection:
        names = {
            row[0]
            for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert {"tenants", "reports", "decisions", "change_notes", "events"}.issubset(names)


def test_at_021_decisions_and_independent_notes(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    session = _sessions(engine)
    context, _review_id, report_id, change_id = create_local_graph(session, slug="local")
    workspace = TenantWorkspace(session, context)
    assert workspace.get_decision(report_id, change_id).version == 0
    reviewed = workspace.set_decision(
        report_id=report_id,
        change_id=change_id,
        status="reviewed",
        expected_version=0,
        idempotency_key=uuid4(),
        action="reviewed",
    )
    assert reviewed.value.status == "reviewed"
    question = workspace.set_decision(
        report_id=report_id,
        change_id=change_id,
        status="question",
        expected_version=1,
        idempotency_key=uuid4(),
    )
    assert question.value.status == "question"
    blocker = workspace.set_decision(
        report_id=report_id,
        change_id=change_id,
        status="blocker",
        expected_version=2,
        idempotency_key=uuid4(),
        action="blocker",
    )
    assert blocker.value.status == "blocker"
    reopened = workspace.set_decision(
        report_id=report_id,
        change_id=change_id,
        status="unreviewed",
        expected_version=3,
        idempotency_key=uuid4(),
        action="blocker",
    )
    assert reopened.value.status == "unreviewed"
    note = workspace.save_note(
        report_id=report_id,
        change_id=change_id,
        text="needs a test",
        expected_version=0,
        idempotency_key=uuid4(),
    )
    assert note.value.version == 1
    assert workspace.get_decision(report_id, change_id).version == 4
    progress = workspace.progress(report_id)
    assert progress.total == 1
    assert progress.unreviewed == 1
    assert (
        progress.reviewed + progress.question + progress.blocker + progress.unreviewed
        == progress.total
    )
    session.commit()
    session.close()
    engine.dispose()


def test_next_decision_status_matches_tui_actions() -> None:
    assert next_decision_status("unreviewed", "reviewed") == "reviewed"
    assert next_decision_status("reviewed", "reopen") == "unreviewed"
    assert next_decision_status("unreviewed", "blocker") == "blocker"
    assert next_decision_status("blocker", "blocker") == "unreviewed"


def test_at_022_note_collision_preserves_both_drafts(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    first = _sessions(engine)
    context, _review_id, report_id, change_id = create_local_graph(first, slug="notes")
    first.commit()
    second = _sessions(engine)
    writer = TenantWorkspace(first, context)
    other = TenantWorkspace(second, context)
    writer.save_note(
        report_id=report_id,
        change_id=change_id,
        text="first draft",
        expected_version=0,
        idempotency_key=uuid4(),
    )
    first.commit()
    with pytest.raises(VersionConflict) as caught:
        other.save_note(
            report_id=report_id,
            change_id=change_id,
            text="second draft",
            expected_version=0,
            idempotency_key=uuid4(),
        )
    assert caught.value.note.text == "first draft"
    replaced = other.save_note(
        report_id=report_id,
        change_id=change_id,
        text="second draft",
        expected_version=caught.value.note.version,
        idempotency_key=uuid4(),
    )
    second.commit()
    assert replaced.value.text == "second draft"
    first.close()
    second.close()
    engine.dispose()


def test_stale_note_conflicts_even_when_text_matches(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    session = _sessions(engine)
    context, _review_id, report_id, change_id = create_local_graph(session, slug="same-text")
    workspace = TenantWorkspace(session, context)
    workspace.save_note(
        report_id=report_id,
        change_id=change_id,
        text="same",
        expected_version=0,
        idempotency_key=uuid4(),
    )
    with pytest.raises(VersionConflict):
        workspace.save_note(
            report_id=report_id,
            change_id=change_id,
            text="same",
            expected_version=0,
            idempotency_key=uuid4(),
        )
    session.close()
    engine.dispose()


def test_at_023_idempotent_retry_writes_one_history_event(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    session = _sessions(engine)
    context, _review_id, report_id, change_id = create_local_graph(session, slug="retry")
    workspace = TenantWorkspace(session, context)
    key = uuid4()
    first = workspace.set_decision(
        report_id=report_id,
        change_id=change_id,
        status="reviewed",
        expected_version=0,
        idempotency_key=key,
    )
    replay = workspace.set_decision(
        report_id=report_id,
        change_id=change_id,
        status="reviewed",
        expected_version=0,
        idempotency_key=key,
    )
    assert replay.replayed is True
    assert replay.value.version == first.value.version
    assert workspace.review_event_count(report_id, change_id, "decision") == 1
    with pytest.raises(IdempotencyConflict):
        workspace.set_decision(
            report_id=report_id,
            change_id=change_id,
            status="blocker",
            expected_version=0,
            idempotency_key=key,
        )
    session.close()
    engine.dispose()


def test_at_024_new_report_starts_unreviewed(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    session = _sessions(engine)
    context, review_id, report_id, change_id = create_local_graph(session, slug="revision")
    workspace = TenantWorkspace(session, context)
    workspace.set_decision(
        report_id=report_id,
        change_id=change_id,
        status="reviewed",
        expected_version=0,
        idempotency_key=uuid4(),
    )
    workspace.save_note(
        report_id=report_id,
        change_id=change_id,
        text="approved this snapshot",
        expected_version=0,
        idempotency_key=uuid4(),
    )
    other_change = uuid4()
    new_report = workspace.add_report(
        review_id=review_id,
        snapshot_id=workspace.get_report(report_id).snapshot_id,
        kind="static",
        content_digest="1" * 64,
        config_digest="2" * 64,
        changes=[(other_change, "C1", 0)],
    )
    historical = workspace.get_decision(report_id, change_id)
    assert historical.status == "reviewed"
    assert workspace.get_note(report_id, change_id).text == "approved this snapshot"
    assert workspace.get_decision(new_report.id, other_change).status == "unreviewed"
    assert workspace.get_note(new_report.id, other_change).text == ""
    assert workspace.get_report(report_id).id == report_id
    session.close()
    engine.dispose()


def test_reports_are_immutable(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    session = _sessions(engine)
    context, _review_id, report_id, _change_id = create_local_graph(session, slug="immut")
    report = session.get(Report, (context.tenant_id, report_id))
    assert report is not None
    report.content_digest = "0" * 64
    with pytest.raises(DBAPIError, match="immutable"):
        session.commit()
    session.rollback()
    session.close()
    engine.dispose()


def test_at_031_tenants_cannot_read_each_other(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    first = _sessions(engine)
    second = _sessions(engine)
    left, _left_review, left_report, left_change = create_local_graph(
        first, slug="alpha", target_key="github:99:482"
    )
    first.commit()
    right, _right_review, right_report, _right_change = create_local_graph(
        second, slug="beta", target_key="github:99:482"
    )
    second.commit()
    left_ws = TenantWorkspace(first, left, artifact_root=tmp_path / "artifacts")
    right_ws = TenantWorkspace(second, right, artifact_root=tmp_path / "artifacts")
    left_ws.set_decision(
        report_id=left_report,
        change_id=left_change,
        status="reviewed",
        expected_version=0,
        idempotency_key=uuid4(),
    )
    artifact = left_ws.put_artifact("report", b"tenant-a")
    job = left_ws.put_job(kind="refresh", status="queued", phase="waiting", dedupe_key="inbox")
    credential = left_ws.put_credential(
        kind="github", ciphertext="cipher", nonce="nonce", key_id="k1"
    )
    left_ws.put_inbox_row(tab="authored", repository_id=uuid4(), pr_number=482, title="secret")
    first.commit()
    with pytest.raises(NotFound):
        right_ws.get_report(left_report)
    with pytest.raises(NotFound):
        right_ws.get_decision(left_report, left_change)
    with pytest.raises(NotFound):
        right_ws.get_job(job.id)
    with pytest.raises(NotFound):
        right_ws.get_credential(credential.id)
    with pytest.raises(NotFound):
        right_ws.get_artifact_bytes(artifact.digest)
    assert right_ws.list_inbox("authored") == []
    assert right_ws.events_after(0) == []
    assert right_ws.get_report(right_report).id == right_report
    first.close()
    second.close()
    engine.dispose()


def test_viewer_cannot_mutate_shared_state(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    session = _sessions(engine)
    context, _review_id, report_id, change_id = create_local_graph(session, slug="viewer")
    viewer = ActorContext(
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        role="viewer",
        correlation_id=uuid4(),
        authorization_version=1,
    )
    membership = session.get(Membership, (context.tenant_id, context.actor_id))
    assert membership is not None
    membership.role = "viewer"
    session.flush()
    workspace = TenantWorkspace(session, viewer)
    with pytest.raises(AccessDenied):
        workspace.set_decision(
            report_id=report_id,
            change_id=change_id,
            status="reviewed",
            expected_version=0,
            idempotency_key=uuid4(),
        )
    session.close()
    engine.dispose()
