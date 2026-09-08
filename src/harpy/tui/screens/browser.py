"""Local analysis and GitHub inbox browser. Does not start analysis."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from harpy.analysis.pipeline import list_browser, load_analysis
from harpy.analysis.workflows.session import OpenInbox, OpenReview
from harpy.models import BrowserItem
from harpy.prefs import PrefsStore
from harpy.tui.browser_rows import (
    BrowserDisplayRow,
    filter_disabled,
    item_key,
    known_repos,
    rows_from_items,
    visible_browser_rows,
)
from harpy.tui.cards import freshness_header
from harpy.tui.screens.repo_filter import RepoFilterDialog

TABS = ("local", "authored", "assigned", "review-requested", "tracked")


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
        Binding("space", "toggle_fold", "Fold"),
        Binding("h,left", "fold", "Fold", show=False),
        Binding("l,right", "unfold", "Unfold", show=False),
        Binding("enter", "open", "Open"),
        Binding("f", "filter_repos", "Repos"),
        Binding("o", "toggle_open", "Open PRs"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        offline: bool = False,
        root: Path | None = None,
        items: list[BrowserItem] | None = None,
        prefs: PrefsStore | None = None,
    ) -> None:
        super().__init__()
        self.offline = offline
        self.root = root
        self._prefs = prefs
        self.tab = "local"
        self._listed: list[BrowserItem] = items or []
        self._disabled = set(prefs.load_disabled_repos()) if prefs is not None else set()
        self._open_only = True
        self._items = filter_disabled(self._listed, self._disabled)
        self._rows: list[BrowserDisplayRow] = []
        self._visible: list[BrowserDisplayRow] = []
        self._collapsed: set[str] = set()
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
        self._reload(refresh_remote=not self.offline)
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
        if self._visible:
            self._cursor = min(self._cursor + 1, len(self._visible) - 1)
            self._paint()

    def action_cursor_up(self) -> None:
        if self._visible:
            self._cursor = max(self._cursor - 1, 0)
            self._paint()

    def action_toggle_fold(self) -> None:
        self._fold(toggle=True)

    def action_fold(self) -> None:
        self._fold(toggle=False, collapse=True)

    def action_unfold(self) -> None:
        self._fold(toggle=False, collapse=False)

    def action_refresh(self) -> None:
        if self.offline:
            self._status = "offline — showing cached rows"
            self._paint()
            return
        self._reload(refresh_remote=True)

    def action_toggle_open(self) -> None:
        self._open_only = not self._open_only
        self._reload(refresh_remote=not self.offline)

    def action_filter_repos(self) -> None:
        repos = self._known_repos()
        self.push_screen(RepoFilterDialog(repos, set(self._disabled)), self._repos_chosen)

    def _repos_chosen(self, disabled: set[str] | None) -> None:
        if disabled is None:
            return
        self._disabled = set(disabled)
        if self._prefs is not None:
            self._prefs.save_disabled_repos(self._disabled)
        self._apply_listed(keep_cursor=True)
        hidden = ""
        if len(self._disabled) == 1:
            hidden = "  ·  1 repo hidden"
        elif self._disabled:
            hidden = f"  ·  {len(self._disabled)} repos hidden"
        mode = "offline" if self.offline else "online"
        self._status = f"{mode}  ·  {len(self._items)} rows{hidden}"
        self._paint()

    def _known_repos(self) -> list[str]:
        local = list_browser("local", offline=True, root=self.root, open_only=False)
        names = {*known_repos(local), *known_repos(self._listed), *self._disabled}
        return sorted(names)

    def action_open(self) -> None:
        row = self._current_row()
        if row is None:
            return
        if row.kind == "repo":
            children = [
                child
                for child in self._rows
                if child.parent_key == row.node_key and child.item is not None
            ]
            only = children[0].item if len(children) == 1 else None
            if row.node_key in self._collapsed and only is not None:
                self._open_item(only)
                return
            self._fold(toggle=True)
            return
        if row.item is None:
            return
        self._open_item(row.item)

    def _open_item(self, item: BrowserItem) -> None:
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
        self._listed = list_browser(
            self.tab,
            offline=self.offline,
            root=self.root,
            refresh_remote=refresh_remote and not self.offline,
            open_only=self._open_only,
        )
        self._apply_listed(keep_cursor=keep_cursor)
        errors = [item.query_error for item in self._listed if item.query_error]
        mode = "offline" if self.offline else "online"
        extra = f"  ·  {errors[0]}" if errors else ""
        cached = next((item.cached_at for item in self._listed if item.cached_at), "")
        cache_note = f"  ·  cached {cached}" if cached and (self.offline or errors) else ""
        trunc = "  ·  showing first 20" if any(item.truncated for item in self._listed) else ""
        hidden = f"  ·  {len(self._disabled)} repo hidden" if len(self._disabled) == 1 else ""
        if len(self._disabled) > 1:
            hidden = f"  ·  {len(self._disabled)} repos hidden"
        scope = "open PRs" if self._open_only else "all PRs"
        self._status = (
            f"{mode}  ·  {scope}  ·  {len(self._items)} rows{cache_note}{trunc}{hidden}{extra}"
        )
        self._paint()
        if focused == "browser-rows":
            self.query_one("#browser-rows").focus()

    def _apply_listed(self, *, keep_cursor: bool = False) -> None:
        previous = None
        current = self._current_item()
        if keep_cursor and current is not None:
            previous = item_key(current)
        self._items = filter_disabled(self._listed, self._disabled)
        self._rows = rows_from_items(self._items)
        repo_keys = {row.node_key for row in self._rows if row.has_children}
        if keep_cursor:
            self._collapsed &= repo_keys
        else:
            self._collapsed = set(repo_keys)
        self._visible = visible_browser_rows(self._rows, self._collapsed)
        if previous:
            self._cursor = next(
                (
                    index
                    for index, row in enumerate(self._visible)
                    if row.item is not None and item_key(row.item) == previous
                ),
                self._first_review_index(),
            )
        else:
            self._cursor = self._first_review_index()

    def _paint(self) -> None:
        tabs = "  ".join(("▸" + name if name == self.tab else name) for name in TABS)
        self.query_one("#browser-tabs", Static).update(tabs)
        current = self._current_item()
        row = self._current_row()
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
        elif row is not None and row.kind == "repo":
            self.query_one("#freshness", Static).update(row.label)
        else:
            self.query_one("#freshness", Static).update("No rows in this tab")
        body = self.query_one("#browser-rows", VerticalScroll)
        body.remove_children()
        if not self._visible:
            body.mount(Static("No reviews in this tab", classes="tree-row", shrink=True))
        else:
            body.mount(
                *[
                    Static(
                        row.render(
                            selected=index == self._cursor,
                            collapsed=row.node_key in self._collapsed,
                        ),
                        classes="tree-row tree-"
                        + row.kind
                        + (" -selected" if index == self._cursor else ""),
                        shrink=True,
                        markup=False,
                    )
                    for index, row in enumerate(self._visible)
                ]
            )
        self.query_one("#status", Static).update(self._status)

    def _current_row(self) -> BrowserDisplayRow | None:
        if not self._visible or not (0 <= self._cursor < len(self._visible)):
            return None
        return self._visible[self._cursor]

    def _current_item(self) -> BrowserItem | None:
        row = self._current_row()
        return row.item if row is not None else None

    def _first_review_index(self) -> int:
        for index, row in enumerate(self._visible):
            if row.kind == "review":
                return index
        return 0

    def _fold(self, *, toggle: bool, collapse: bool = True) -> None:
        row = self._current_row()
        if row is None:
            return
        key = row.node_key if row.has_children else row.parent_key
        if not key:
            return
        previous = item_key(row.item) if row.item is not None else None
        if toggle:
            if key in self._collapsed:
                self._collapsed.discard(key)
            else:
                self._collapsed.add(key)
        elif collapse:
            self._collapsed.add(key)
        else:
            self._collapsed.discard(key)
        self._visible = visible_browser_rows(self._rows, self._collapsed)
        if previous:
            self._cursor = next(
                (
                    index
                    for index, item in enumerate(self._visible)
                    if item.item is not None and item_key(item.item) == previous
                ),
                next(
                    (index for index, item in enumerate(self._visible) if item.node_key == key), 0
                ),
            )
        else:
            self._cursor = next(
                (index for index, item in enumerate(self._visible) if item.node_key == key),
                0,
            )
        self._paint()


def run_browser(
    *,
    offline: bool = False,
    root: Path | None = None,
    prefs: PrefsStore | None = None,
) -> OpenReview | OpenInbox | None:
    return BrowserApp(offline=offline, root=root, prefs=prefs or PrefsStore()).run()
