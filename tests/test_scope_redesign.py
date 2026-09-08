from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, OptionList, Static

from harpy.config import DEFAULT_MODEL
from harpy.models import ScopePreset, ScopeSelection
from harpy.prefs import PrefsStore
from harpy.review_scope import default_selection
from harpy.tui.scope_rows import SCOPE_COPY, run_details, run_summary
from harpy.tui.screens.scope_controls import ScopeCheckList, ScopePicker, ScopePresetName
from harpy.tui.screens.scope_dialog import ScopeDialog

OTHER_MODEL = "another-model-with-a-long-exact-provider-id"


class DialogApp(App[None]):
    def __init__(self, selection: ScopeSelection, store: PrefsStore) -> None:
        super().__init__()
        self.dialog = ScopeDialog(
            selection,
            models=[DEFAULT_MODEL, OTHER_MODEL],
            store=store,
            default_model=DEFAULT_MODEL,
        )
        self.results: list[ScopeSelection | None] = []

    def compose(self) -> ComposeResult:
        yield Button("Open", id="opener")

    def on_mount(self) -> None:
        self.query_one(Button).focus()
        self.push_screen(self.dialog, self.results.append)


def rendered(widget: Static) -> str:
    return str(widget.render())


@pytest.mark.asyncio
async def test_keyboard_selection_is_in_place_and_empty_cannot_start(tmp_path: Path) -> None:
    original = default_selection()
    app = DialogApp(original, PrefsStore(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        checks = app.dialog.query_one(ScopeCheckList)
        first = checks.query_one("#scope-check-changes")
        assert checks.has_focus
        for _ in range(7):
            await pilot.press("space", "down")
        assert app.dialog.query_one("#scope-start", Button).disabled
        assert "Select at least one check" in rendered(
            app.dialog.query_one("#scope-summary", Static)
        )
        await pilot.press("enter")
        assert isinstance(app.screen, ScopeDialog)
        assert checks.query_one("#scope-check-changes") is first
        assert all(original.enabled.values())
        await pilot.press("escape")
        assert app.results == [None]
        assert app.query_one("#opener").has_focus


@pytest.mark.asyncio
async def test_diagram_dependency_keyboard_and_mouse(tmp_path: Path) -> None:
    app = DialogApp(default_selection(), PrefsStore(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#scope-check-api")
        await pilot.click("#scope-check-db")
        assert not app.dialog._selection.enabled["diagrams"]
        await pilot.click("#scope-check-diagrams")
        assert not app.dialog._selection.enabled["diagrams"]
        assert "Select API contracts" in rendered(
            app.dialog.query_one("#scope-focused-help", Static)
        )
        await pilot.click("#scope-check-api")
        assert not app.dialog._selection.enabled["diagrams"]
        await pilot.click("#scope-check-diagrams")
        assert app.dialog._selection.enabled["diagrams"]
        await pilot.click("#scope-check-tests")
        assert "does not run tests" in rendered(app.dialog.query_one("#scope-focused-help", Static))


@pytest.mark.asyncio
async def test_model_picker_enter_never_starts_and_global_updates_disabled_checks(
    tmp_path: Path,
) -> None:
    selection = default_selection()
    selection.enabled["tests"] = False
    selection.models["security"] = OTHER_MODEL
    app = DialogApp(selection, PrefsStore(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        assert "Multiple models" in str(app.dialog.query_one("#scope-model", Button).label)
        await pilot.click("#scope-model")
        assert isinstance(app.screen, ScopePicker)
        app.screen.query_one(OptionList).highlighted = 1
        await pilot.pause()
        assert OTHER_MODEL in rendered(app.screen.query_one("#scope-picker-detail", Static))
        await pilot.press("enter")
        assert isinstance(app.screen, ScopeDialog)
        assert app.results == []
        assert set(app.dialog._selection.models.values()) == {OTHER_MODEL}
        assert not app.dialog._selection.enabled["tests"]
        assert "1 planned AI call" in rendered(app.dialog.query_one("#scope-summary", Static))


@pytest.mark.asyncio
async def test_override_editor_survives_collapse_and_escape_closes_editor(tmp_path: Path) -> None:
    app = DialogApp(default_selection(), PrefsStore(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#scope-customize")
        button = app.dialog.query_one("#scope-model-security", Button)
        button.focus()
        await pilot.press("enter")
        assert isinstance(app.screen, ScopePicker)
        await pilot.press("down", "enter")
        assert app.dialog._selection.models["security"] == OTHER_MODEL
        assert "2 planned AI calls" in rendered(app.dialog.query_one("#scope-summary", Static))
        await pilot.press("escape")
        assert isinstance(app.screen, ScopeDialog)
        assert not app.dialog.query_one("#scope-model-editor").display
        assert app.dialog._selection.models["security"] == OTHER_MODEL
        assert app.dialog.query_one("#scope-customize").has_focus


@pytest.mark.asyncio
async def test_preset_picker_preview_apply_and_cancel_preserves_saved_selection(
    tmp_path: Path,
) -> None:
    store = PrefsStore(tmp_path)
    original = default_selection()
    store.save_selection(original)
    app = DialogApp(original, store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#scope-preset")
        options = app.screen.query_one(OptionList)
        options.highlighted = 4
        await pilot.pause()
        assert "1 check" in rendered(app.screen.query_one("#scope-picker-detail", Static))
        assert app.screen.query_one("#scope-picker-delete", Button).disabled
        await pilot.press("enter")
        assert app.dialog._selection.preset == "Fast triage"
        assert sum(app.dialog._selection.enabled.values()) == 1
        assert app.results == []
        await pilot.press("escape")
    assert store.load_selection() == original


@pytest.mark.asyncio
async def test_save_replace_requires_explicit_action_and_survives_cancel(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    selection = default_selection()
    store.save_preset(ScopePreset(name="Mine", enabled=selection.enabled, models=selection.models))
    app = DialogApp(selection, store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("space")
        await pilot.click("#scope-save")
        assert isinstance(app.screen, ScopePresetName)
        field = app.screen.query_one(Input)
        field.value = "Everything"
        await pilot.press("enter")
        assert isinstance(app.screen, ScopePresetName)
        assert "Built-in" in rendered(app.screen.query_one("#scope-name-note", Static))
        field.value = "Mine"
        await pilot.press("enter")
        assert isinstance(app.screen, ScopePresetName)
        assert store.user_presets()[0].enabled["changes"]
        await pilot.click("#scope-name-replace")
        assert isinstance(app.screen, ScopeDialog)
        assert app.dialog._selection.preset == "Mine"
        assert not store.user_presets()[0].enabled["changes"]
        assert app.results == []
        await pilot.press("escape")
        assert app.results == [None]
    assert not store.user_presets()[0].enabled["changes"]


@pytest.mark.asyncio
async def test_delete_active_preset_keeps_selection_custom(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    selection = default_selection()
    selection.enabled["tests"] = False
    selection.preset = "[bold]My review[/bold]"
    store.save_preset(
        ScopePreset(name=selection.preset, enabled=selection.enabled, models=selection.models)
    )
    app = DialogApp(selection, store)
    async with app.run_test(size=(120, 40)) as pilot:
        assert "[bold]" in str(app.dialog.query_one("#scope-preset", Button).label)
        await pilot.click("#scope-preset")
        assert not app.screen.query_one("#scope-picker-delete", Button).disabled
        await pilot.click("#scope-picker-delete")
        await pilot.press("escape")
        assert app.dialog._selection.enabled == selection.enabled
        assert app.dialog._selection.models == selection.models
        assert app.dialog._selection.preset is None
        assert "Custom" in str(app.dialog.query_one("#scope-preset", Button).label)
    assert store.user_presets() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(120, 40), (100, 30), (80, 24)])
async def test_layout_pinned_actions_focus_trap_and_resize(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    app = DialogApp(default_selection(), PrefsStore(tmp_path))
    async with app.run_test(size=size) as pilot:
        start = app.dialog.query_one("#scope-start", Button)
        assert start.region.bottom <= size[1] - 1
        assert start.region.right <= size[0] - 2
        for _ in range(7):
            await pilot.press("down")
        checks = app.dialog.query_one(ScopeCheckList)
        assert checks.selected_scope.id == "diagrams"
        selected = checks.query_one("#scope-check-diagrams")
        viewport = app.dialog.query_one("#scope-body").content_region
        assert selected.region.intersection(viewport).height >= 1
        assert start.region.bottom <= size[1] - 1
        for _ in range(16):
            await pilot.press("tab")
            assert app.focused is not None
            assert app.focused.screen is app.dialog
        checks.focus()
        await pilot.resize_terminal(80 if size[0] > 80 else 120, 24 if size[1] > 24 else 40)
        assert checks.has_focus
        assert checks.selected_scope.id == "diagrams"
        assert checks.query_one("#scope-check-diagrams") is selected
        assert "run again" in rendered(app.dialog.query_one("#scope-rerun-note", Static))


def test_summary_is_call_plan_and_grouped_copy_covers_all_scopes() -> None:
    selection = default_selection()
    assert {item.id for item in SCOPE_COPY} == set(selection.enabled)
    assert (
        run_summary(selection, default_model=DEFAULT_MODEL)
        == "7 checks + diagrams · 1 planned AI call"
    )
    selection.models["security"] = OTHER_MODEL
    details = run_details(selection, default_model=DEFAULT_MODEL)
    assert "after grouping" in details
    assert OTHER_MODEL in details
    assert "repair call" in details
