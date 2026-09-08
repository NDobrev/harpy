from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from harpy.models import LogicalChange, ReviewStatus
from harpy.tui.workspace import inspector_card


class ContextPanel(VerticalScroll):
    BINDINGS = [
        *VerticalScroll.BINDINGS,
        Binding("j", "scroll_down", "Scroll", show=False),
        Binding("k", "scroll_up", "Scroll", show=False),
    ]
    can_focus_children = False

    def compose(self) -> ComposeResult:
        yield Static(id="context-body", shrink=True)

    def show(
        self,
        change: LogicalChange | None,
        *,
        banner: str | None,
        status: ReviewStatus = ReviewStatus.UNREVIEWED,
        text: str | None = None,
        head_sha: str = "",
    ) -> None:
        body = self.query_one("#context-body", Static)
        body.update(text or inspector_card(change, status=status, banner=banner, head_sha=head_sha))
