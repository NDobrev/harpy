from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from harpy.analysis.workflows.browser import persist_analysis
from harpy.analysis.workflows.session import load_review_session, save_review_session
from harpy.models import AnalysisResult, BrowserItem, LogicalChange, PullRequest, ReviewStatus
from harpy.storage.backend import read_marker
from harpy.storage.db import ReviewStore
from harpy.storage.engine import SqliteUnavailableError, create_sqlite_engine
from harpy.storage.legacy import ImportError, ImportRefused, import_legacy_root
from harpy.storage.schema import LegacyHumanWork, Preset, Report
from harpy.storage.workspace import ActorContext, TenantWorkspace
from harpy.tui.workspace import session_from_workspace, workspace_from_result


def _result() -> AnalysisResult:
    return AnalysisResult(
        pr=PullRequest(
            number=11,
            title="resume me",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="dddddddddddd",
            additions=1,
            deletions=0,
            repo="acme/pay",
        ),
        changes=[
            LogicalChange(id="C1", title="auth"),
            LogicalChange(id="C2", title="docs"),
        ],
    )


def _seed_legacy(tmp_path: Path) -> BrowserItem:
    item = persist_analysis(_result(), root=tmp_path)
    assert item.review_id is not None
    state = workspace_from_result(_result())
    state.select("C2", None)
    state.set_lens("questions")
    state.mark(ReviewStatus.REVIEWED)
    state.add_note("check deny path")
    session = session_from_workspace(item.review_id, state, _result())
    session.statuses["C99"] = "reviewed"
    save_review_session(session, root=tmp_path)
    store = ReviewStore(tmp_path)
    store.add_note(item.review_id, "review-level leftover")
    store.close()
    (tmp_path / "presets.json").write_text(
        json.dumps([{"name": "Everything", "enabled": {"changes": True}, "models": {}}]),
        encoding="utf-8",
    )
    return item


def test_at_036_legacy_import_preserves_human_work(tmp_path: Path) -> None:
    item = _seed_legacy(tmp_path)
    assert item.review_id is not None
    first = import_legacy_root(tmp_path, apply=True)
    assert first.state == "completed"
    assert first.backup_dir is not None
    assert first.backup_dir.is_dir()
    assert (first.backup_dir / "MANIFEST.json").is_file()
    marker = read_marker(tmp_path)
    assert marker is not None
    assert marker.import_id == first.import_id
    loaded = load_review_session(item.review_id, root=tmp_path)
    assert loaded is not None
    assert loaded.statuses["C2"] == "reviewed"
    assert loaded.notes["C2"] == "check deny path"
    assert loaded.selected_id == "C2"
    engine = create_sqlite_engine(tmp_path / marker.database)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    try:
        report = db.get(Report, (marker.tenant_id, item.report_id))
        assert report is not None
        assert report.id == item.report_id
        leftovers = list(
            db.scalars(select(LegacyHumanWork).where(LegacyHumanWork.tenant_id == marker.tenant_id))
        )
        assert any(row.original_change_ref == "C99" for row in leftovers)
        assert any(row.reason == "review-level-note" for row in leftovers)
        presets = list(db.scalars(select(Preset).where(Preset.tenant_id == marker.tenant_id)))
        assert any(row.name == "Everything (imported)" for row in presets)
        assert first.warnings
    finally:
        db.close()
        engine.dispose()
    (tmp_path / "storage-backend.json").unlink()
    resumed = import_legacy_root(tmp_path, apply=True)
    assert resumed.import_id == first.import_id
    assert read_marker(tmp_path) is not None
    browser = tmp_path / "browser.json"
    browser.chmod(0o644)
    payload = json.loads(browser.read_text(encoding="utf-8"))
    payload["tamper"] = True
    browser.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ImportRefused, match="source changed"):
        import_legacy_root(tmp_path, apply=True)


def test_at_025_navigation_save_does_not_clobber_shared_state(tmp_path: Path) -> None:
    item = persist_analysis(_result(), root=tmp_path)
    assert item.review_id is not None
    state = workspace_from_result(_result())
    state.select("C2", None)
    state.mark(ReviewStatus.REVIEWED)
    state.add_note("tui note")
    save_review_session(session_from_workspace(item.review_id, state, _result()), root=tmp_path)
    imported = import_legacy_root(tmp_path, apply=True)
    loaded = load_review_session(item.review_id, root=tmp_path)
    assert loaded is not None
    assert loaded.statuses["C2"] == "reviewed"
    marker = read_marker(tmp_path)
    assert marker is not None
    engine = create_sqlite_engine(tmp_path / marker.database)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    try:
        workspace = TenantWorkspace(
            db,
            ActorContext(
                tenant_id=imported.tenant_id,
                actor_id=imported.actor_id,
                role="administrator",
                correlation_id=uuid4(),
                authorization_version=1,
            ),
        )
        report_id = workspace.latest_report_id(item.review_id)
        assert report_id is not None
        change_id = workspace.change_ids_for(report_id)["C2"]
        workspace.set_decision(
            report_id=report_id,
            change_id=change_id,
            status="blocker",
            expected_version=1,
            idempotency_key=uuid4(),
        )
        workspace.save_note(
            report_id=report_id,
            change_id=change_id,
            text="web note",
            expected_version=1,
            idempotency_key=uuid4(),
        )
        db.commit()
    finally:
        db.close()
        engine.dispose()
    loaded.lens = "tests"
    loaded.selected_id = "C1"
    save_review_session(loaded, root=tmp_path)
    again = load_review_session(item.review_id, root=tmp_path)
    assert again is not None
    assert again.statuses["C2"] == "blocker"
    assert again.notes["C2"] == "web note"
    assert again.lens == "tests"
    assert again.selected_id == "C1"


def test_at_037_corrupt_newer_readonly_and_missing_sqlite_fail_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review = tmp_path / "review.json"
    browser = tmp_path / "browser.json"
    review.write_text("{", encoding="utf-8")
    browser.write_text("{}", encoding="utf-8")
    with pytest.raises(ImportError, match="review.json"):
        import_legacy_root(tmp_path, apply=True)
    assert review.read_text(encoding="utf-8") == "{"
    assert not (tmp_path / "storage-backend.json").exists()

    review.write_text(json.dumps({"schema_version": 99, "reports": {}}), encoding="utf-8")
    with pytest.raises(ImportRefused, match="newer"):
        import_legacy_root(tmp_path, apply=True)
    assert not (tmp_path / "storage-backend.json").exists()

    review.write_text(json.dumps({"schema_version": 1, "reports": {}}), encoding="utf-8")
    original_browser = browser.read_text(encoding="utf-8")
    tmp_path.chmod(0o555)
    try:
        with pytest.raises(ImportError):
            import_legacy_root(tmp_path, apply=True)
    finally:
        tmp_path.chmod(0o755)
    assert browser.read_text(encoding="utf-8") == original_browser
    assert not (tmp_path / "storage-backend.json").exists()

    def _unavailable() -> object:
        raise SqliteUnavailableError("no sqlite")

    monkeypatch.setattr("harpy.storage.engine.sqlite_module", _unavailable)
    with pytest.raises(SqliteUnavailableError):
        import_legacy_root(tmp_path, apply=True)
    assert not (tmp_path / "storage-backend.json").exists()
    assert browser.read_text(encoding="utf-8") == original_browser
