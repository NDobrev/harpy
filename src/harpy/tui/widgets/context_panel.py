from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from harpy.models import LogicalChange


class ContextPanel(VerticalScroll):
    BINDINGS = [
        *VerticalScroll.BINDINGS,
        Binding("j", "scroll_down", "Scroll", show=False),
        Binding("k", "scroll_up", "Scroll", show=False),
    ]
    can_focus_children = False

    def compose(self) -> ComposeResult:
        yield Static(id="context-body", shrink=True)

    def show(self, change: LogicalChange | None, *, banner: str | None) -> None:
        body = self.query_one("#context-body", Static)
        if change is None:
            body.update(banner or "")
            return
        parts = [
            "OVERVIEW",
            "",
            f"Importance: {change.importance:.0f}",
            f"Risk: {change.risk}",
            f"Confidence: {change.confidence:.0%}",
            f"Unexpectedness: {change.unexpectedness:.0f}%",
            "",
            "BEFORE",
            "",
            change.before or "(static only)",
            "",
            "AFTER",
            "",
            change.after or "(static only)",
            "",
            "WHY",
            "",
            change.why or "",
            "",
            "AFFECTS",
            "",
            *([f"• {item}" for item in change.affected_components] or ["• (unknown)"]),
            "",
            "REVIEW QUESTIONS",
            "",
            *([f"• {item}" for item in change.review_questions] or ["• (none)"]),
            "",
            "POSSIBLE OMISSIONS",
            "",
            *([f"• {item}" for item in change.possible_omissions] or ["• (none)"]),
        ]
        if banner:
            parts = [banner, ""] + parts
        body.update("\n".join(parts))
