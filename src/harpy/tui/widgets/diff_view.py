from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from harpy.models import AnalysisResult, LogicalChange
from harpy.tui.file_diff import DiffSection, annotated_file_sections


class DiffView(VerticalScroll):
    BINDINGS = [
        *VerticalScroll.BINDINGS,
        Binding("j", "scroll_down", "Scroll", show=False),
        Binding("k", "scroll_up", "Scroll", show=False),
        Binding("n,right_square_bracket", "next_change", "Next change"),
        Binding("p,left_square_bracket", "prev_change", "Prev change"),
    ]
    can_focus_children = False

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._jump: list[Widget] = []
        self._jump_index = 0

    def compose(self) -> ComposeResult:
        yield Static("No change selected", id="diff-empty", shrink=True)

    def show(
        self,
        result: AnalysisResult,
        change: LogicalChange | None,
        *,
        file_path: str | None = None,
        changes: list[LogicalChange] | None = None,
    ) -> None:
        self.remove_children()
        self._jump = []
        self._jump_index = 0
        if change is None:
            self.mount(Static("No change selected", classes="diff-section", shrink=True))
            return
        sections = annotated_file_sections(
            result,
            change,
            file_path=file_path,
            changes=changes or result.changes,
        )
        widgets: list[Widget] = []
        for section in sections:
            widget = _mount_section(section)
            widgets.append(widget)
            if section.kind == "change" and section.current:
                self._jump.append(widget)
        if widgets:
            self.mount(*widgets)
        if self._jump:
            self.call_after_refresh(self._activate, 0)
            return
        self.scroll_home(animate=False)

    def action_next_change(self) -> None:
        self._step(1)

    def action_prev_change(self) -> None:
        self._step(-1)

    def _step(self, delta: int) -> None:
        if not self._jump:
            return
        self._jump_index = (self._jump_index + delta) % len(self._jump)
        self._activate(self._jump_index)

    def _activate(self, jump_index: int) -> None:
        self._jump_index = jump_index
        target = self._jump[jump_index]
        for widget in self.query(".diff-row"):
            widget.set_class(widget is target, "-active")
        self.scroll_to_widget(target, animate=False)


def _mount_section(section: DiffSection) -> Widget:
    if section.kind != "change" or not section.gutter:
        return Static(section.text, classes="diff-section", shrink=True, markup=False)
    gutter = Static(section.gutter, classes=_gutter_classes(section), markup=False, shrink=True)
    code = Static(section.text, classes="diff-code", markup=False, shrink=True)
    row = Horizontal(gutter, code, classes=_row_classes(section))
    return row


def _gutter_classes(section: DiffSection) -> str:
    classes = "diff-gutter"
    if section.current:
        return f"{classes} diff-gutter-current"
    if section.accent == "dodger_blue2":
        return f"{classes} diff-gutter-blue"
    return f"{classes} diff-gutter-orange"


def _row_classes(section: DiffSection) -> str:
    classes = "diff-row"
    if section.current:
        return f"{classes} diff-current"
    return f"{classes} diff-other"
