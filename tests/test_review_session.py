from __future__ import annotations

from pathlib import Path

from harpy.analysis.workflows.browser import persist_analysis
from harpy.analysis.workflows.session import load_review_session, save_review_session
from harpy.models import AnalysisResult, LogicalChange, PullRequest, ReviewStatus
from harpy.tui.app import HarpyApp
from harpy.tui.workspace import apply_session, session_from_workspace, workspace_from_result


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


def test_same_pr_keeps_review_id(tmp_path: Path) -> None:
    first = persist_analysis(_result(), root=tmp_path)
    second = persist_analysis(_result(), root=tmp_path)
    assert first.review_id == second.review_id


def test_session_survives_new_workspace(tmp_path: Path) -> None:
    item = persist_analysis(_result(), root=tmp_path)
    assert item.review_id is not None
    state = workspace_from_result(_result())
    state.select("C2", None)
    state.set_lens("questions")
    state.mark(ReviewStatus.REVIEWED)
    state.add_note("check deny path")
    save_review_session(session_from_workspace(item.review_id, state, _result()), root=tmp_path)
    session = load_review_session(item.review_id, root=tmp_path)
    assert session is not None
    restored = workspace_from_result(_result())
    apply_session(restored, session, _result())
    assert restored.selected_id == "C2"
    assert restored.lens == "questions"
    assert restored.statuses["C2"] == ReviewStatus.REVIEWED
    assert restored.notes["C2"] == "check deny path"


def test_tui_quit_restores_marks_and_selection(tmp_path: Path) -> None:
    item = persist_analysis(_result(), root=tmp_path)
    assert item.review_id is not None
    first = HarpyApp(_result(), review_id=item.review_id, store_root=tmp_path)
    first.workspace.select("C2")
    first.selected_id = "C2"
    first.workspace.mark(ReviewStatus.REVIEWED)
    first.workspace.add_note("needs audit")
    first.workspace.set_lens("tests")
    first._persist_context()
    second = HarpyApp(_result(), review_id=item.review_id, store_root=tmp_path)
    assert second.selected_id == "C2"
    assert second.workspace.lens == "tests"
    assert second.workspace.statuses["C2"] == ReviewStatus.REVIEWED
    assert second.workspace.notes["C2"] == "needs audit"
    listed = persist_analysis(_result(), root=tmp_path)
    assert listed.review_progress == "1/2"
