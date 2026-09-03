from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from harpy.config import SELECTABLE_MODELS, HarpyConfig
from harpy.models import AnalysisResult, LogicalChange, ScopeCall, ScopeSelection
from harpy.prefs import PrefsStore
from harpy.review_scope import plan_calls, signature
from harpy.tui.impact_entries import change_for_impact, entries_from_result
from harpy.tui.screens.scope_dialog import ScopeDialog
from harpy.tui.widgets.api_detail import ApiDetail
from harpy.tui.widgets.api_diagram import ApiDiagramView
from harpy.tui.widgets.api_list import ApiList
from harpy.tui.widgets.change_list import ChangeList
from harpy.tui.widgets.context_panel import ContextPanel
from harpy.tui.widgets.diff_view import DiffView
from harpy.tui.widgets.status_bar import StatusBar

_REVIEW_PANES = ("changes", "diff", "context")
_API_PANES = ("api-list", "api-diagram", "api-detail")
_API_FILE_PANES = ("api-list", "diff", "api-detail")


class HarpyApp(App[None]):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("tab", "focus_next_pane", "Pane", priority=True),
        Binding("e", "expand", "Expand"),
        Binding("c", "collapse", "Collapse noise"),
        Binding("a", "all", "All"),
        Binding("i", "api_view", "Impact"),
        Binding("escape", "leave_api", "Back", show=False),
        Binding("s", "scope", "Scope"),
        Binding("r", "questions", "Questions"),
        Binding("t", "tests", "Tests"),
        Binding("o", "omissions", "Omissions"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        result: AnalysisResult,
        *,
        config: HarpyConfig | None = None,
        prefs: PrefsStore | None = None,
    ) -> None:
        super().__init__()
        self.result = result
        self.config = config
        self.selected_id: str | None = result.changes[0].id if result.changes else None
        self.selected_file: str | None = None
        self.expanded = False
        self.hide_noise = False
        self.api_mode = False
        self.api_index = 0
        self.api_file: str | None = None
        self._progress_i = 0
        self._progress_label = "Analyzing semantic changes"
        self._semantic_running = False
        self._semantic_allowed = bool(
            config is not None
            and config.semantic.enabled
            and (result.pending_semantic or result.semantic_available)
        )
        self._plan: list[ScopeCall] | None = None
        self._scope_signature = ""
        self._prefs = prefs or PrefsStore()

    def compose(self) -> ComposeResult:
        yield Header()
        yield ApiList(id="api-list")
        yield ChangeList(id="changes")
        yield ApiDiagramView(id="api-diagram")
        yield DiffView(id="diff")
        yield ApiDetail(id="api-detail")
        yield ContextPanel(id="context")
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._set_api_visible(False)
        self._refresh()
        self.query_one(ChangeList).focus()

    def _tick_progress(self) -> None:
        if not self._semantic_running:
            return
        self._progress_i = (self._progress_i + 1) % 3
        self.query_one(StatusBar).set_text(f"{self._progress_label}{'.' * (self._progress_i + 1)}")

    def _set_progress(self, message: str) -> None:
        self._progress_label = message
        self.query_one(StatusBar).set_text(message)

    def action_scope(self) -> None:
        if not self._semantic_allowed or self.config is None:
            return
        if self._semantic_running:
            self.notify("Semantic analysis already running")
            return
        store = self._prefs
        models = self.config.selectable_models or SELECTABLE_MODELS
        dialog = ScopeDialog(
            store.load_selection(),
            models=models,
            presets=store.all_presets(),
            store=store,
            default_model=self.config.semantic.model,
        )
        self.push_screen(dialog, self._scope_chosen)

    def _scope_chosen(self, picked: ScopeSelection | None) -> None:
        if picked is None or self.config is None:
            return
        self._prefs.save_selection(picked)
        self._plan = plan_calls(picked, default_model=self.config.semantic.model)
        self._scope_signature = signature(picked, default_model=self.config.semantic.model)
        self._semantic_running = True
        self.result.pending_semantic = True
        self._progress_label = "Analyzing semantic changes"
        self.set_interval(0.5, self._tick_progress)
        self.run_worker(self._run_semantic, exclusive=True, thread=True)

    def _run_semantic(self) -> None:
        from harpy.analysis.pipeline import apply_semantic

        assert self.config is not None

        def progress(message: str) -> None:
            self.call_from_thread(self._set_progress, message)

        try:
            updated = apply_semantic(
                self.result,
                config=self.config,
                plan=self._plan,
                force=True,
                progress=progress,
                scope_signature=self._scope_signature,
            )
        except Exception as exc:  # noqa: BLE001
            self.result.pending_semantic = False
            self.result.banner = (
                f"Semantic analysis unavailable. Showing static review priority only. ({exc})"
            )
            updated = self.result
        self.call_from_thread(self._apply_updated, updated)

    def _apply_updated(self, updated: AnalysisResult) -> None:
        self._semantic_running = False
        self.result = updated
        visible = self._visible()
        if self.selected_id not in {change.id for change in visible}:
            self.selected_id = visible[0].id if visible else None
            self.selected_file = None
        self._refresh()

    def _visible(self) -> list[LogicalChange]:
        changes = self.result.changes
        if self.hide_noise:
            changes = [
                item for item in changes if item.risk not in {"LOW"} or item.importance >= 20
            ]
        return changes

    def _current(self) -> LogicalChange | None:
        visible = self._visible()
        by_id = {change.id: change for change in visible}
        if self.selected_id in by_id:
            return by_id[self.selected_id]
        if not visible:
            self.selected_id = None
            return None
        self.selected_id = visible[0].id
        return visible[0]

    def _status_text(self) -> str:
        if self.api_mode:
            focused = self.focused.id if self.focused is not None else "api-list"
            if self.api_file:
                hint = {
                    "api-list": "j/k files  tab pane  i back",
                    "diff": "j/k scroll  n/p this context  tab pane",
                    "api-detail": "j/k scroll  i back",
                }.get(focused or "", "i back")
            else:
                hint = {
                    "api-list": "j/k items  space fold  tab pane  i back",
                    "api-diagram": self.query_one(ApiDiagramView).status_hint(),
                    "api-detail": "j/k scroll  i back",
                }.get(focused or "", "i back")
            return f"{_impact_status(self.result)}  ·  {hint}"
        focused = self.focused.id if self.focused is not None else "changes"
        hint = {
            "changes": "j/k move  space fold  i impact  s scope  tab pane",
            "diff": "j/k scroll  n/p this context  tab pane",
            "context": "j/k scroll context  tab pane",
        }.get(focused or "", "tab pane")
        if self.result.banner:
            return f"{self.result.banner}  ·  {hint}"
        if self.result.semantic_available:
            return f"Semantic analysis ready  ·  {hint}"
        if self._semantic_running:
            return f"{self._progress_label}  ·  {hint}"
        if self._semantic_allowed:
            return f"Semantic analysis not started  ·  s scope  ·  {hint}"
        return f"Static review priority only.  ·  {hint}"

    def on_change_list_cursor_moved(self, event: ChangeList.CursorMoved) -> None:
        if event.change_id is None:
            return
        if event.change_id == self.selected_id and event.file_path == self.selected_file:
            return
        self.selected_id = event.change_id
        self.selected_file = event.file_path
        self.expanded = False
        self._show_panes()

    def on_api_list_cursor_moved(self, event: ApiList.CursorMoved) -> None:
        self.api_index = event.index
        self.api_file = event.file_path
        self._show_api()

    def on_api_diagram_view_node_selected(self, event: ApiDiagramView.NodeSelected) -> None:
        self.api_file = event.path
        items = entries_from_result(self.result)
        self.query_one(ApiList).populate(
            items, selected=self.api_index, selected_file=self.api_file
        )
        self._show_api()

    def _impact_panes(self) -> tuple[str, ...]:
        if self.api_file:
            return _API_FILE_PANES
        return _API_PANES

    def action_focus_next_pane(self) -> None:
        panes = self._impact_panes() if self.api_mode else _REVIEW_PANES
        current = self.focused.id if self.focused is not None else panes[0]
        try:
            index = panes.index(current)
        except ValueError:
            index = -1
        next_id = panes[(index + 1) % len(panes)]
        self.query_one(f"#{next_id}").focus()
        self.query_one(StatusBar).set_text(self._status_text())

    def action_api_view(self) -> None:
        if self.api_mode:
            self.api_mode = False
            self._set_api_visible(False)
            self.query_one(ChangeList).focus()
            self._show_panes()
            return
        if not entries_from_result(self.result):
            self.notify("No endpoint or database contract changes")
            return
        self.api_mode = True
        self.api_index = 0
        self.api_file = None
        self._set_api_visible(True)
        self.query_one(ApiList).populate(entries_from_result(self.result), selected=0)
        self.query_one(ApiList).focus()
        self._show_api()

    def action_leave_api(self) -> None:
        if self.api_mode:
            self.action_api_view()

    def _set_api_visible(self, visible: bool) -> None:
        self.screen.set_class(visible, "-impact")
        for pane_id in _REVIEW_PANES:
            self.query_one(f"#{pane_id}").display = not visible
        for pane_id in _API_PANES:
            self.query_one(f"#{pane_id}").display = visible

    def _refresh(self) -> None:
        if self.api_mode:
            items = entries_from_result(self.result)
            if not items:
                self.api_mode = False
                self._set_api_visible(False)
            else:
                self.api_index = min(self.api_index, len(items) - 1)
                self.query_one(ApiList).populate(
                    items, selected=self.api_index, selected_file=self.api_file
                )
                self._show_api()
                return
        visible = self._visible()
        current = self._current()
        self.query_one(ChangeList).populate(
            visible,
            hunks=self.result.hunks,
            selected_id=current.id if current else None,
            selected_file=self.selected_file,
        )
        self._show_panes()

    def _show_panes(self) -> None:
        current = self._current()
        self.query_one(DiffView).show(
            self.result,
            current,
            file_path=None if self.expanded else self.selected_file,
            changes=self._visible(),
        )
        self.query_one(ContextPanel).show(current, banner=self.result.banner)
        self.query_one(StatusBar).set_text(self._status_text())

    def _show_api(self) -> None:
        items = entries_from_result(self.result)
        item = items[self.api_index] if items and 0 <= self.api_index < len(items) else None
        file_path = self.api_file if item is not None else None
        showing_diff = bool(file_path)
        self.query_one("#changes").display = False
        self.query_one("#context").display = False
        self.query_one("#api-list").display = True
        self.query_one("#api-detail").display = True
        self.query_one("#api-diagram").display = not showing_diff
        self.query_one("#diff").display = showing_diff
        self.query_one(ApiDetail).show(item)
        self.query_one(ApiDiagramView).show(item, db_impacts=self.result.db_impacts)
        if showing_diff and item is not None and file_path is not None:
            change = change_for_impact(self.result, item, file_path)
            self.query_one(DiffView).show(
                self.result,
                change,
                file_path=file_path,
                changes=self._visible(),
            )
        self.query_one(StatusBar).set_text(self._status_text())

    def action_expand(self) -> None:
        if self.api_mode:
            return
        self.expanded = not self.expanded
        self._show_panes()

    def action_collapse(self) -> None:
        if self.api_mode:
            return
        self.hide_noise = not self.hide_noise
        self.selected_id = None
        self.selected_file = None
        self._refresh()

    def action_all(self) -> None:
        if self.api_mode:
            return
        self.hide_noise = False
        self._refresh()

    def action_questions(self) -> None:
        current = self._current()
        if current:
            self.notify("\n".join(current.review_questions) or "No questions")

    def action_tests(self) -> None:
        current = self._current()
        if current:
            self.notify("\n".join(current.tests) or "No tests listed")

    def action_omissions(self) -> None:
        current = self._current()
        if current:
            self.notify("\n".join(current.possible_omissions) or "No omissions listed")


def _impact_status(result: AnalysisResult) -> str:
    api_n = len(result.api_impacts)
    db_n = len(result.db_impacts)
    parts: list[str] = []
    if api_n:
        parts.append(f"{api_n} endpoint{'s' if api_n != 1 else ''}")
    if db_n:
        parts.append(f"{db_n} schema change{'s' if db_n != 1 else ''}")
    legend = "cyan API  blue DB  orange BL  fuchsia SEC  red breaking"
    if not parts:
        return f"Impact · empty  ·  {legend}"
    return "Impact · " + " · ".join(parts) + f"  ·  {legend}"


def run_tui(
    result: AnalysisResult,
    *,
    config: HarpyConfig | None = None,
    prefs: PrefsStore | None = None,
) -> None:
    HarpyApp(result, config=config, prefs=prefs).run()
