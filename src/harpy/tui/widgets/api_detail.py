from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from harpy.tui.impact_entries import ImpactEntry, impact_tone

_TONES = ("impact-api", "impact-db", "impact-bl", "impact-sec", "impact-breaking")


class ApiDetail(VerticalScroll):
    BINDINGS = [
        *VerticalScroll.BINDINGS,
        Binding("j", "scroll_down", show=False),
        Binding("k", "scroll_up", show=False),
    ]
    can_focus_children = False

    def compose(self) -> ComposeResult:
        yield Static(id="api-detail-body", shrink=True)

    def show(self, item: ImpactEntry | None) -> None:
        for tone in _TONES:
            self.remove_class(tone)
        body = self.query_one("#api-detail-body", Static)
        if item is None:
            body.update("No change selected")
            return
        self.add_class(f"impact-{impact_tone(item)}")
        if item.db is not None:
            body.update(_db_text(item))
            return
        if item.api is not None:
            body.update(_api_text(item))
            return
        body.update("No change selected")


def _api_text(item: ImpactEntry) -> str:
    api = item.api
    assert api is not None
    breaking = "BREAKING" if api.breaking else "Not a breaking contract change"
    parts = [
        f"{api.method} {api.path}".strip() or api.summary,
        "",
        breaking,
        api.breaking_reason if api.breaking else "",
        "",
        "WHAT CHANGED",
        "",
        api.summary,
        "",
        "BEFORE",
        "",
        api.before or "(not described)",
        "",
        "AFTER",
        "",
        api.after or "(not described)",
        "",
        "IMPACT",
        "",
        api.impact or "(not described)",
        "",
        "CALLERS",
        "",
        *([f"• {caller}" for caller in api.callers] or ["• (none listed)"]),
        "",
        *_scope_lines(item),
    ]
    return "\n".join(part for part in parts if part is not None)


def _db_text(item: ImpactEntry) -> str:
    db = item.db
    assert db is not None
    breaking = "BREAKING" if db.breaking else "Not a breaking schema change"
    heading = f"{db.operation} {db.target}".strip() or db.summary
    parts = [
        heading,
        "",
        breaking,
        db.breaking_reason if db.breaking else "",
        "",
        "WHAT CHANGED",
        "",
        db.summary,
        "",
        "BEFORE",
        "",
        db.before or "(not described)",
        "",
        "AFTER",
        "",
        db.after or "(not described)",
        "",
        "IMPACT",
        "",
        db.impact or "(not described)",
        "",
        "OBJECTS",
        "",
        *([f"• {name}" for name in db.objects] or ["• (none listed)"]),
        "",
        *_scope_lines(item),
    ]
    return "\n".join(part for part in parts if part is not None)


def _scope_lines(item: ImpactEntry) -> list[str]:
    bl = [
        "BUSINESS LOGIC",
        "",
        "Impacted" if item.business_logic else "Not impacted",
    ]
    if item.business_logic and item.business_logic_why:
        bl.append(item.business_logic_why)
    sec = [
        "SECURITY",
        "",
        "Impacted" if item.security else "Not impacted",
    ]
    if item.security and item.security_why:
        sec.append(item.security_why)
    files = ["FILES", ""]
    if not item.files:
        files.append("• (none listed)")
    else:
        last = len(item.files) - 1
        files.extend(
            f"{'└─ ' if index == last else '├─ '}{path}" for index, path in enumerate(item.files)
        )
    return [*bl, "", *sec, "", *files]
