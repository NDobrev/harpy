"""Focused selection controls for analysis configuration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from harpy.models import ScopeSelection
from harpy.prefs import PrefsStore
from harpy.review_scope import short_model_label
from harpy.tui.scope_rows import SCOPE_COPY, ScopeCopy, diagrams_available


class ScopeCheckRow(Static):
    class Activated(Message):
        def __init__(self, scope_id: str) -> None:
            super().__init__()
            self.scope_id = scope_id

    def __init__(self, copy: ScopeCopy) -> None:
        super().__init__(id=f"scope-check-{copy.id}", classes="scope-check", markup=False)
        self.copy = copy
        self.tooltip = copy.help

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Activated(self.copy.id))


class ScopeCheckList(VerticalScroll):
    can_focus_children = False
    BINDINGS = [
        Binding("j,down", "move(1)", "Next", show=False),
        Binding("k,up", "move(-1)", "Previous", show=False),
        Binding("space", "toggle_check", "Toggle", show=False),
        Binding("enter", "run", "Start analysis", show=False),
    ]

    class Highlighted(Message):
        pass

    class Toggled(Message):
        def __init__(self, scope_id: str) -> None:
            super().__init__()
            self.scope_id = scope_id

    class RunRequested(Message):
        pass

    def __init__(self) -> None:
        super().__init__(id="scope-rows")
        self.cursor = 0
        self._selection = ScopeSelection()
        self._base_model = ""
        self._compact = False

    @property
    def selected_scope(self) -> ScopeCopy:
        return SCOPE_COPY[self.cursor]

    def compose(self) -> ComposeResult:
        for item in SCOPE_COPY:
            if item.group:
                yield Static(item.group, classes="scope-group", markup=False)
            yield ScopeCheckRow(item)

    def update_selection(
        self, selection: ScopeSelection, *, base_model: str, compact: bool
    ) -> None:
        self._selection = selection
        self._base_model = base_model
        self._compact = compact
        self._paint()

    def _paint(self) -> None:
        for index, item in enumerate(SCOPE_COPY):
            row = self.query_one(f"#scope-check-{item.id}", ScopeCheckRow)
            selected = index == self.cursor
            unavailable = item.id == "diagrams" and not diagrams_available(self._selection)
            mark = "[✓]" if self._selection.enabled.get(item.id, False) else "[ ]"
            cursor = "›" if selected and self.has_focus else " "
            text = Text(f"{cursor} {mark} {item.label}")
            model = self._selection.models.get(item.id)
            if model and model != self._base_model:
                text.append(f" · {short_model_label(model)}", style="italic")
            if unavailable:
                text.append(" · unavailable", style="dim")
            elif not self._compact:
                text.append(" " * max(2, 29 - len(item.label)) + item.description, style="dim")
            row.update(text)
            row.set_class(selected and self.has_focus, "-selected")
            row.set_class(unavailable, "-unavailable")

    def on_focus(self) -> None:
        self._paint()
        self.post_message(self.Highlighted())

    def on_blur(self) -> None:
        self._paint()

    def action_move(self, step: int) -> None:
        self.cursor = (self.cursor + step) % len(SCOPE_COPY)
        self._paint()
        self.reveal_selection()
        self.post_message(self.Highlighted())

    def reveal_selection(self) -> None:
        self.query_one(f"#scope-check-{self.selected_scope.id}").scroll_visible(
            animate=False, force=True
        )

    def action_toggle_check(self) -> None:
        self.post_message(self.Toggled(self.selected_scope.id))

    def action_run(self) -> None:
        self.post_message(self.RunRequested())

    def on_scope_check_row_activated(self, event: ScopeCheckRow.Activated) -> None:
        event.stop()
        self.cursor = next(
            index for index, item in enumerate(SCOPE_COPY) if item.id == event.scope_id
        )
        self.focus()
        self._paint()
        self.post_message(self.Highlighted())
        self.post_message(self.Toggled(event.scope_id))


@dataclass(frozen=True)
class PickerChoice:
    key: str
    label: str
    detail: str
    deletable: bool = False


class ScopePicker(ModalScreen[str | None]):
    CSS_PATH = "../scope_dialog.tcss"
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(
        self,
        title: str,
        choices: Sequence[PickerChoice],
        *,
        current: str | None = None,
        store: PrefsStore | None = None,
    ) -> None:
        super().__init__()
        self.heading = title
        self.choices = list(choices)
        self.current = current
        self.store = store

    def compose(self) -> ComposeResult:
        with Vertical(classes="scope-popup"):
            yield Static(self.heading, classes="scope-title", markup=False)
            yield OptionList(
                *(Option(Text(choice.label), id=choice.key) for choice in self.choices),
                id="scope-picker-options",
            )
            yield Static(id="scope-picker-detail", markup=False)
            with Horizontal(classes="scope-actions"):
                yield Button("Delete preset", id="scope-picker-delete", disabled=True)
                yield Button("Cancel", id="scope-picker-cancel")
                yield Button("Select", id="scope-picker-select", variant="primary")

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.highlighted = (
            next((index for index, item in enumerate(self.choices) if item.key == self.current), 0)
            if self.choices
            else None
        )
        self.query_one("#scope-picker-delete").display = self.store is not None
        self._update_detail()
        options.focus()

    def _choice(self) -> PickerChoice | None:
        index = self.query_one(OptionList).highlighted
        return self.choices[index] if index is not None and index < len(self.choices) else None

    def _update_detail(self) -> None:
        choice = self._choice()
        self.query_one("#scope-picker-detail", Static).update(
            choice.detail if choice else "No choices available."
        )
        self.query_one("#scope-picker-select", Button).disabled = choice is None
        self.query_one("#scope-picker-delete", Button).disabled = not (
            choice and choice.deletable and self.store
        )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        self._update_detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._pick()

    def _pick(self) -> None:
        choice = self._choice()
        if choice:
            self.dismiss(choice.key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "scope-picker-cancel":
            self.dismiss(None)
        elif event.button.id == "scope-picker-select":
            self._pick()
        elif event.button.id == "scope-picker-delete":
            choice = self._choice()
            if choice and choice.deletable and self.store:
                try:
                    deleted = self.store.delete_preset(choice.key)
                except OSError as exc:
                    self.query_one("#scope-picker-detail", Static).update(
                        f"Could not delete: {exc}"
                    )
                    return
                if deleted:
                    self.choices.remove(choice)
                    options = self.query_one(OptionList)
                    options.clear_options().add_options(
                        Option(Text(item.label), id=item.key) for item in self.choices
                    )
                    options.highlighted = 0 if self.choices else None
                    options.focus()
                    self._update_detail()

    def action_cancel(self) -> None:
        self.dismiss(None)


class ScopePresetName(ModalScreen[str | None]):
    CSS_PATH = "../scope_dialog.tcss"
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, *, builtins: set[str], existing: set[str]) -> None:
        super().__init__()
        self.builtins = builtins
        self.existing = existing

    def compose(self) -> ComposeResult:
        with Vertical(classes="scope-popup"):
            yield Static("Save preset", classes="scope-title")
            yield Input(placeholder="Preset name", id="scope-name-input")
            yield Static(
                "Enter a name for these checks and models.", id="scope-name-note", markup=False
            )
            with Horizontal(classes="scope-actions"):
                yield Button("Cancel", id="scope-name-cancel")
                yield Button("Save", id="scope-name-save", variant="primary", disabled=True)
                yield Button("Replace", id="scope-name-replace", variant="warning", disabled=True)

    def on_mount(self) -> None:
        self.query_one("#scope-name-replace").display = False
        self.query_one(Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        name = event.value.strip()
        builtin = name in self.builtins
        collision = name in self.existing and not builtin
        self.query_one("#scope-name-save", Button).disabled = not name or builtin or collision
        replacement = self.query_one("#scope-name-replace", Button)
        replacement.display = collision
        replacement.disabled = not collision
        note = "Enter a name for these checks and models."
        if builtin:
            note = "Built-in presets cannot be replaced. Choose another name."
        elif collision:
            note = "This preset exists. Choose Replace explicitly, or enter another name."
        self.query_one("#scope-name-note", Static).update(note)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if not self.query_one("#scope-name-save", Button).disabled:
            self.dismiss(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "scope-name-cancel":
            self.dismiss(None)
        elif event.button.id in {"scope-name-save", "scope-name-replace"}:
            if not event.button.disabled:
                self.dismiss(self.query_one(Input).value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)
