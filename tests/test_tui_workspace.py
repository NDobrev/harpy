from __future__ import annotations

import pytest
from textual.binding import Binding

from harpy.models import (
    AnalysisResult,
    ApiEndpointImpact,
    DiffHunk,
    LogicalChange,
    PullRequest,
    ReviewStatus,
    SequenceDiagram,
    SequenceStep,
)
from harpy.tui.app import HarpyApp
from harpy.tui.screens.palette import HELP_TEXT, CommandPalette
from harpy.tui.widgets.api_list import ApiList
from harpy.tui.widgets.change_list import ChangeList
from harpy.tui.widgets.diff_view import DiffView
from harpy.tui.workspace import PALETTE_ACTIONS


def _result() -> AnalysisResult:
    return AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="abc",
            additions=1,
            deletions=0,
        ),
        changes=[
            LogicalChange(
                id="C1",
                title="auth",
                review_questions=["who can call this?"],
                possible_omissions=["audit log"],
                tests=["test_auth"],
                files=["src/auth.py"],
            ),
            LogicalChange(id="C2", title="docs", files=["README.md"]),
        ],
    )


def test_analysis_action_uses_analyze_label() -> None:
    binding = next(
        item for item in HarpyApp.BINDINGS if isinstance(item, Binding) and item.action == "scope"
    )
    palette_action = next(item for item in PALETTE_ACTIONS if item.id == "scope")

    assert binding.description == "Analyze"
    assert palette_action.title == "Analyze"
    assert "s  analyze" in HELP_TEXT


@pytest.mark.asyncio
async def test_questions_stay_in_inspector() -> None:
    app = HarpyApp(_result())
    async with app.run_test(size=(160, 48)) as pilot:
        await pilot.press("r")
        body = str(app.query_one("#context-body").render())
        assert "who can call this?" in body
        assert app.workspace.lens == "questions"
        assert app.selected_id == "C1"


@pytest.mark.asyncio
async def test_palette_opens_and_runs_questions() -> None:
    app = HarpyApp(_result())
    async with app.run_test(size=(160, 48)) as pilot:
        await pilot.press("ctrl+p")
        assert isinstance(app.screen, CommandPalette)
        await pilot.press("q", "u", "e")
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, CommandPalette)
        assert app.workspace.lens == "questions"


@pytest.mark.asyncio
async def test_late_update_does_not_steal_focus() -> None:
    app = HarpyApp(_result())
    async with app.run_test(size=(160, 48)) as pilot:
        app.query_one(ChangeList).focus()
        await pilot.pause()
        focused = app.focused.id if app.focused is not None else None
        app._apply_updated(app.result.model_copy(deep=True), app._active_run)
        assert app.focused is not None
        assert app.focused.id == focused


@pytest.mark.asyncio
async def test_search_filters_without_letter_shortcut() -> None:
    app = HarpyApp(_result())
    async with app.run_test(size=(160, 48)) as pilot:
        await pilot.press("slash")
        await pilot.press("d", "o", "c", "s")
        await pilot.pause()
        visible = app._visible()
        assert [item.id for item in visible] == ["C2"]
        assert app.workspace.entering_text
        await pilot.press("v")
        assert app.workspace.statuses.get("C1") != ReviewStatus.REVIEWED
        await pilot.press("escape")
        assert app.workspace.entering_text is False


def _result_with_diff() -> AnalysisResult:
    hunk = DiffHunk(
        id="H1",
        file_path="src/auth.py",
        old_start=1,
        old_count=0,
        new_start=1,
        new_count=1,
        patch="@@ -1,0 +1,1 @@\n+deny\n",
    )
    return AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="abc",
            additions=1,
            deletions=0,
        ),
        hunks=[hunk],
        changes=[
            LogicalChange(
                id="C1",
                title="auth",
                files=["src/auth.py"],
                hunk_ids=["H1"],
            ),
            LogicalChange(id="C2", title="docs", files=["README.md"]),
        ],
    )


@pytest.mark.asyncio
async def test_search_keystrokes_do_not_crash_diff() -> None:
    app = HarpyApp(_result_with_diff())
    async with app.run_test(size=(160, 48)) as pilot:
        await pilot.press("slash")
        await pilot.press("a")
        await pilot.press("u")
        await pilot.press("t")
        await pilot.press("z")
        await pilot.pause()
        assert [item.id for item in app._visible()] == []


@pytest.mark.asyncio
async def test_zoom_fills_the_focused_pane() -> None:
    app = HarpyApp(_result())
    async with app.run_test(size=(160, 48)) as pilot:
        diff = app.query_one(DiffView)
        diff.focus()
        await pilot.pause()
        before = diff.size.width
        await pilot.press("z")
        await pilot.pause()
        assert app.workspace.maximized
        assert app.screen.has_class("-zoomed")
        assert app.query_one("#diff").display is True
        assert app.query_one("#changes").display is False
        assert app.query_one("#context").display is False
        assert diff.size.width > before
        assert diff.size.width >= 140
        await pilot.press("z")
        await pilot.pause()
        assert app.workspace.maximized is False
        assert not app.screen.has_class("-zoomed")
        assert app.query_one("#changes").display is True


def _result_with_impact() -> AnalysisResult:
    return AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="abc",
            additions=1,
            deletions=0,
        ),
        changes=[
            LogicalChange(id="C1", title="settle", files=["src/routes/v1.ts"]),
        ],
        api_impacts=[
            ApiEndpointImpact(
                change_id="C1",
                method="POST",
                path="/v1/settle",
                files=["src/routes/v1.ts"],
                sequence=SequenceDiagram(
                    actors=["Ops", "API"],
                    steps=[SequenceStep(from_actor="Ops", to_actor="API", message="POST settle")],
                ),
            )
        ],
    )


@pytest.mark.asyncio
async def test_review_trees_start_with_file_branches_collapsed() -> None:
    review = HarpyApp(_result_with_diff())
    async with review.run_test(size=(160, 48)):
        changes = review.query_one(ChangeList)
        assert any(row.kind == "change" for row in changes._visible)
        assert all(row.kind != "file" for row in changes._visible)

    impact = HarpyApp(_result_with_impact())
    async with impact.run_test(size=(160, 48)) as pilot:
        await pilot.press("i")
        entries = impact.query_one(ApiList)
        assert [row.kind for row in entries._visible] == ["impact"]


@pytest.mark.asyncio
async def test_impact_tab_cycles_visible_panes() -> None:
    app = HarpyApp(_result_with_impact())
    async with app.run_test(size=(160, 48)) as pilot:
        await pilot.press("i")
        await pilot.pause()
        assert app.api_mode
        assert app.focused is not None
        assert app.focused.id == "api-list"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None
        assert app.focused.id == "api-diagram"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None
        assert app.focused.id == "api-detail"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None
        assert app.focused.id == "api-list"


@pytest.mark.asyncio
async def test_impact_zoom_fills_the_focused_pane() -> None:
    app = HarpyApp(_result_with_impact())
    async with app.run_test(size=(160, 48)) as pilot:
        await pilot.press("i")
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        diagram = app.query_one("#api-diagram")
        before = diagram.size.width
        await pilot.press("z")
        await pilot.pause()
        assert app.workspace.maximized
        assert app.screen.has_class("-zoomed")
        assert diagram.display is True
        assert app.query_one("#api-list").display is False
        assert app.query_one("#api-detail").display is False
        assert diagram.size.width > before
        assert diagram.size.width >= 140
        await pilot.press("z")
        await pilot.pause()
        assert app.workspace.maximized is False
        assert not app.screen.has_class("-zoomed")
        assert app.query_one("#api-list").display is True
        assert app.query_one("#api-detail").display is True
