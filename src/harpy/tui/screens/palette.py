"""Command palette for every workspace action."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from harpy.tui.workspace import PALETTE_ACTIONS, PaletteAction


class CommandPalette(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("enter", "pick", "Run", show=False),
        Binding("j", "down", "Down", show=False),
        Binding("k", "up", "Up", show=False),
        Binding("down", "down", "Down", show=False),
        Binding("up", "up", "Up", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._index = 0
        self._visible = list(PALETTE_ACTIONS)

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-box"):
            yield Input(placeholder="Command…", id="palette-input")
            yield Static(id="palette-rows")

    def on_mount(self) -> None:
        self._render_rows()
        self.query_one(Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        needle = event.value.strip().lower()
        self._visible = [
            item
            for item in PALETTE_ACTIONS
            if not needle or needle in item.title.lower() or needle in item.id
        ]
        self._index = 0
        self._render_rows()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.action_pick()

    def action_down(self) -> None:
        if self._visible:
            self._index = (self._index + 1) % len(self._visible)
            self._render_rows()

    def action_up(self) -> None:
        if self._visible:
            self._index = (self._index - 1) % len(self._visible)
            self._render_rows()

    def action_pick(self) -> None:
        if not self._visible:
            self.dismiss(None)
            return
        self.dismiss(self._visible[self._index].id)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _render_rows(self) -> None:
        lines = [
            _row(item, selected=index == self._index) for index, item in enumerate(self._visible)
        ]
        self.query_one("#palette-rows", Static).update("\n".join(lines) or "No commands")


def _row(item: PaletteAction, *, selected: bool) -> str:
    mark = "▸" if selected else " "
    return f"{mark} {item.title}  ({item.keys})"


HELP_TEXT = """
j/k arrows  move        tab  cycle panes
/  search               ctrl+p  palette
s  analyze              e  expand diff
i  impact               r t o  questions/tests/omissions
v  reviewed             V  reopen        b  blocker
m  note                 z  maximize
escape  back            q  quit
""".strip()


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,enter,q,question_mark", "close", "Close", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static(HELP_TEXT, id="help-body")

    def action_close(self) -> None:
        self.dismiss(None)


class NoteDialog(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Close", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="note-box"):
            yield Input(placeholder="Note…", id="note-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.dismiss(text or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
