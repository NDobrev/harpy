"""Local analysis and GitHub inbox browser. Does not start analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from harpy.analysis.pipeline import list_browser, load_analysis
from harpy.analysis.workflows.session import OpenInbox, OpenReview
from harpy.models import BrowserItem, Freshness
from harpy.tui.cards import freshness_header

TABS = ("local", "authored", "assigned", "review-requested", "tracked")


@dataclass(frozen=True)
class BrowserRow:
    review_id: UUID
    title: str
    source: str
    freshness: Freshness
    offline: bool = False


def row_label(item: BrowserItem, *, selected: bool) -> str:
    cursor = "▸ " if selected else "  "
    repo = f"{item.repo}#{item.number}" if item.repo and item.number is not None else item.source
    badge = item.freshness.value.replace("_", " ")
    progress = item.review_progress or item.completeness or "no local report"
    rev = item.analyzed_rev or "—"
    latest = item.latest_rev or "—"
    author = f" · {item.author}" if item.author else ""
    ci = f" · {item.ci_summary}" if item.ci_summary else ""
    return (
        f"{cursor}{repo}  {item.title or '(untitled)'}{author}\n"
        f"    analyzed {rev}  latest {latest}  {badge}  {progress}{ci}"
    )


class BrowserApp(App[OpenReview | OpenInbox | None]):
    ENABLE_COMMAND_PALETTE = False
    CSS_PATH = str(Path(__file__).resolve().parents[1] / "browser.tcss")
    BINDINGS = [
        Binding("1", "tab_local", "Local"),
        Binding("2", "tab_authored", "Authored"),
        Binding("3", "tab_assigned", "Assigned"),
        Binding("4", "tab_requested", "Requested"),
        Binding("5", "tab_tracked", "Tracked"),
        Binding("tab", "next_tab", "Tab", priority=True),
        Binding("j,down", "cursor_down", "Down", show=False),
        Binding("k,up", "cursor_up", "Up", show=False),
        Binding("enter", "open", "Open"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        offline: bool = False,
        root: Path | None = None,
        items: list[BrowserItem] | None = None,
    ) -> None:
        super().__init__()
        self.offline = offline
        self.root = root
        self.tab = "local"
        self._items = items or []
        self._cursor = 0
        self._status = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="browser-tabs")
        yield Static(id="freshness")
        yield VerticalScroll(id="browser-rows")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._reload()
        self.set_interval(120, self._tick_refresh)

    def _tick_refresh(self) -> None:
        if not self.offline:
            self._reload(keep_cursor=True, refresh_remote=True)

    def action_tab_local(self) -> None:
        self._set_tab("local")

    def action_tab_authored(self) -> None:
        self._set_tab("authored")

    def action_tab_assigned(self) -> None:
        self._set_tab("assigned")

    def action_tab_requested(self) -> None:
        self._set_tab("review-requested")

    def action_tab_tracked(self) -> None:
        self._set_tab("tracked")

    def action_next_tab(self) -> None:
        index = TABS.index(self.tab) if self.tab in TABS else 0
        self._set_tab(TABS[(index + 1) % len(TABS)])

    def _set_tab(self, tab: str) -> None:
        self.tab = tab
        self._cursor = 0
        self._reload()

    def action_cursor_down(self) -> None:
        if self._items:
            self._cursor = min(self._cursor + 1, len(self._items) - 1)
            self._paint()

    def action_cursor_up(self) -> None:
        if self._items:
            self._cursor = max(self._cursor - 1, 0)
            self._paint()

    def action_refresh(self) -> None:
        if self.offline:
            self._status = "offline — showing cached rows"
            self._paint()
            return
        self._reload(refresh_remote=True)

    def action_open(self) -> None:
        if not self._items:
            return
        item = self._items[self._cursor]
        if item.has_local_report and item.review_id is not None:
            loaded = load_analysis(item.review_id, root=self.root)
            if loaded is None:
                self._status = "Persisted report is missing on disk"
                self._paint()
                return
            self.exit(OpenReview(result=loaded, review_id=item.review_id))
            return
        if self.offline or not item.repo or item.number is None:
            self._status = "No local analysis. Listing does not clone or analyze. Use harpy review."
            self._paint()
            return
        self.exit(OpenInbox(repo=item.repo, number=item.number, title=item.title))

    def _reload(self, *, keep_cursor: bool = False, refresh_remote: bool = False) -> None:
        focused = self.focused.id if self.focused is not None else None
        previous = None
        if keep_cursor and self._items:
            previous = _key(self._items[self._cursor])
        self._items = list_browser(
            self.tab,
            offline=self.offline,
            root=self.root,
            refresh_remote=refresh_remote and not self.offline,
        )
        if previous:
            for index, item in enumerate(self._items):
                if _key(item) == previous:
                    self._cursor = index
                    break
        elif self._cursor >= len(self._items):
            self._cursor = max(0, len(self._items) - 1)
        errors = [item.query_error for item in self._items if item.query_error]
        mode = "offline" if self.offline else "online"
        extra = f"  ·  {errors[0]}" if errors else ""
        cached = next((item.cached_at for item in self._items if item.cached_at), "")
        cache_note = f"  ·  cached {cached}" if cached and (self.offline or errors) else ""
        trunc = "  ·  showing first 20" if any(item.truncated for item in self._items) else ""
        self._status = f"{mode}  ·  {len(self._items)} rows{cache_note}{trunc}{extra}"
        self._paint()
        if focused == "browser-rows":
            self.query_one("#browser-rows").focus()

    def _paint(self) -> None:
        tabs = "  ".join(("▸" + name if name == self.tab else name) for name in TABS)
        self.query_one("#browser-tabs", Static).update(tabs)
        current = self._items[self._cursor] if self._items else None
        if current is not None:
            header = freshness_header(
                analyzed_rev=current.analyzed_rev or "none",
                analyzed_at=current.analyzed_at or "unknown",
                latest_rev=current.latest_rev or current.analyzed_rev or "unknown",
                checked=current.cached_at or current.updated_at or "unknown",
                freshness=current.freshness,
            )
            self.query_one("#freshness", Static).update(
                f"{header.analyzed}  ·  {header.latest}  ·  {header.badge}"
            )
        else:
            self.query_one("#freshness", Static).update("No rows in this tab")
        body = self.query_one("#browser-rows", VerticalScroll)
        body.remove_children()
        if not self._items:
            body.mount(Static("No reviews in this tab", classes="tree-row", shrink=True))
        else:
            body.mount(
                *[
                    Static(
                        row_label(item, selected=index == self._cursor),
                        classes="tree-row" + (" -selected" if index == self._cursor else ""),
                        shrink=True,
                        markup=False,
                    )
                    for index, item in enumerate(self._items)
                ]
            )
        self.query_one("#status", Static).update(self._status)


def _key(item: BrowserItem) -> str:
    if item.repo and item.number is not None:
        return f"{item.repo}#{item.number}"
    return str(item.review_id or item.title)


def run_browser(
    *, offline: bool = False, root: Path | None = None
) -> OpenReview | OpenInbox | None:
    return BrowserApp(offline=offline, root=root).run()
