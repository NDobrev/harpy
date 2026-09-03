"""Keyboard-first modal for choosing review scopes and models."""

from __future__ import annotations

from collections.abc import Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from harpy.models import ScopePreset, ScopeSelection
from harpy.prefs import PrefsStore
from harpy.review_scope import (
    SCOPES,
    apply_preset,
    matching_preset,
    normalize,
    plan_calls,
)
from harpy.tui.scope_rows import help_line, preset_line, render_row, row_views, summary_line


class ScopeDialog(ModalScreen[ScopeSelection | None]):
    BINDINGS = [
        Binding("j,down", "cursor_down", "Next", show=False),
        Binding("k,up", "cursor_up", "Prev", show=False),
        Binding("space", "toggle_scope", "Toggle"),
        Binding("m", "next_model", "Model"),
        Binding("M", "prev_model", "Model"),
        Binding("p", "next_preset", "Preset"),
        Binding("P", "prev_preset", "Preset"),
        Binding("S", "save_preset", "Save"),
        Binding("x", "delete_preset", "Delete"),
        Binding("enter", "run", "Run"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        selection: ScopeSelection,
        *,
        models: Sequence[str],
        presets: Sequence[ScopePreset] | None = None,
        store: PrefsStore | None = None,
        default_model: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._selection = normalize(selection, default_model=default_model or models[0])
        self._models = tuple(models)
        self._store = store
        self._presets = list(presets) if presets is not None else []
        self._default_model = default_model or models[0]
        self._cursor = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="scope-box"):
            yield Static("", id="scope-preset")
            yield VerticalScroll(id="scope-rows")
            yield Static("", id="scope-note")
            yield Static("", id="scope-summary")
            yield Static(help_line(), id="scope-help")
            yield Input(placeholder="preset name", id="scope-name-input")

    def on_mount(self) -> None:
        self.query_one("#scope-name-input", Input).display = False
        self._refresh()
        self.query_one("#scope-rows").focus()

    def _preset_list(self) -> list[ScopePreset]:
        if self._store is not None:
            return self._store.all_presets()
        return list(self._presets)

    def _naming(self) -> bool:
        return self.query_one("#scope-name-input", Input).has_focus

    def _refresh(self) -> None:
        self._selection = normalize(self._selection, default_model=self._default_model)
        matched = matching_preset(
            self._selection, self._preset_list(), default_model=self._default_model
        )
        self._selection = self._selection.model_copy(update={"preset": matched})
        self.query_one("#scope-preset", Static).update(preset_line(self._selection.preset))
        rows_widget = self.query_one("#scope-rows", VerticalScroll)
        rows_widget.remove_children()
        views = row_views(self._selection, self._cursor, default_model=self._default_model)
        widgets = [
            Static(
                render_row(row),
                classes="scope-row -selected" if row.selected else "scope-row",
            )
            for row in views
        ]
        if widgets:
            rows_widget.mount(*widgets)
        note = ""
        if not self._selection.enabled.get("security", True):
            note = "Security off: security/data dimensions stay 0 and importance drops."
        self.query_one("#scope-note", Static).update(note)
        calls = plan_calls(self._selection, default_model=self._default_model)
        self.query_one("#scope-summary", Static).update(summary_line(calls))

    def action_cursor_down(self) -> None:
        if self._naming():
            return
        self._cursor = (self._cursor + 1) % len(SCOPES)
        self._refresh()

    def action_cursor_up(self) -> None:
        if self._naming():
            return
        self._cursor = (self._cursor - 1) % len(SCOPES)
        self._refresh()

    def action_toggle_scope(self) -> None:
        if self._naming():
            return
        item = SCOPES[self._cursor]
        enabled = dict(self._selection.enabled)
        enabled[item.id] = not enabled.get(item.id, True)
        self._selection = self._selection.model_copy(update={"enabled": enabled, "preset": None})
        self._refresh()

    def action_next_model(self) -> None:
        self._cycle_model(1)

    def action_prev_model(self) -> None:
        self._cycle_model(-1)

    def _cycle_model(self, step: int) -> None:
        if self._naming():
            return
        item = SCOPES[self._cursor]
        if item.kind == "modifier":
            return
        models = list(self._models)
        current = self._selection.models.get(item.id, self._default_model)
        index = models.index(current) if current in models else -1
        models_map = dict(self._selection.models)
        models_map[item.id] = models[(index + step) % len(models)]
        self._selection = self._selection.model_copy(update={"models": models_map, "preset": None})
        self._refresh()

    def action_next_preset(self) -> None:
        self._cycle_preset(1)

    def action_prev_preset(self) -> None:
        self._cycle_preset(-1)

    def _cycle_preset(self, step: int) -> None:
        if self._naming():
            return
        presets = self._preset_list()
        if not presets:
            return
        names = [item.name for item in presets]
        current = self._selection.preset
        index = names.index(current) if current in names else -1
        self._selection = apply_preset(presets[(index + step) % len(presets)])
        self._refresh()

    def action_save_preset(self) -> None:
        if self._naming():
            return
        field = self.query_one("#scope-name-input", Input)
        field.display = True
        field.focus()

    def action_delete_preset(self) -> None:
        if self._naming() or self._store is None:
            return
        name = self._selection.preset
        if name and self._store.delete_preset(name):
            self._selection = apply_preset(self._preset_list()[0])
            self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if name and self._store is not None:
            saved = self._store.save_preset(
                ScopePreset(
                    name=name,
                    enabled=dict(self._selection.enabled),
                    models=dict(self._selection.models),
                )
            )
            if saved:
                self._selection = self._selection.model_copy(update={"preset": name})
            else:
                self.notify("Cannot overwrite a built-in preset")
        event.input.value = ""
        event.input.display = False
        self.query_one("#scope-rows").focus()
        self._refresh()

    def action_run(self) -> None:
        if self._naming():
            return
        self.dismiss(normalize(self._selection, default_model=self._default_model))

    def action_cancel(self) -> None:
        if self._naming():
            field = self.query_one("#scope-name-input", Input)
            field.value = ""
            field.display = False
            self.query_one("#scope-rows").focus()
            return
        self.dismiss(None)
