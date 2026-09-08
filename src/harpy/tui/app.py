from __future__ import annotations

from pathlib import Path
from uuid import UUID

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, Static

from harpy.analysis.pipeline import load_review_session, save_review_session
from harpy.config import SELECTABLE_MODELS, HarpyConfig
from harpy.models import AnalysisResult, LogicalChange, ReviewStatus, ScopeCall, ScopeSelection
from harpy.prefs import PrefsStore
from harpy.review_scope import plan_calls, signature
from harpy.tui.impact_entries import change_for_impact, entries_from_result
from harpy.tui.layout import workspace_layout
from harpy.tui.screens.palette import CommandPalette, HelpScreen, NoteDialog
from harpy.tui.screens.scope_dialog import ScopeDialog
from harpy.tui.widgets.api_detail import ApiDetail
from harpy.tui.widgets.api_diagram import ApiDiagramView
from harpy.tui.widgets.api_list import ApiList
from harpy.tui.widgets.change_list import ChangeList
from harpy.tui.widgets.context_panel import ContextPanel
from harpy.tui.widgets.diff_view import DiffView
from harpy.tui.widgets.status_bar import StatusBar
from harpy.tui.workspace import (
    apply_session,
    coverage_progress,
    lens_inspector,
    review_progress,
    search_changes,
    session_from_workspace,
    workspace_from_result,
)

_REVIEW_PANES = ("changes", "diff", "context")
_API_PANES = ("api-list", "api-diagram", "api-detail")
_API_FILE_PANES = ("api-list", "diff", "api-detail")
_PANE_TO_REGION = {"changes": "navigator", "diff": "canvas", "context": "inspector"}
_REGION_TO_PANE = {region: pane for pane, region in _PANE_TO_REGION.items()}


class HarpyApp(App[None]):
    ENABLE_COMMAND_PALETTE = False
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
        Binding("slash", "search", "Search"),
        Binding("ctrl+p", "palette", "Palette"),
        Binding("question_mark", "help", "Help"),
        Binding("z", "zoom", "Zoom"),
        Binding("v", "reviewed", "Reviewed"),
        Binding("V", "reopen", "Reopen"),
        Binding("b", "blocker", "Blocker"),
        Binding("m", "note", "Note"),
        Binding("alt+left", "nav_back", "Back", show=False),
        Binding("alt+right", "nav_forward", "Forward", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        result: AnalysisResult,
        *,
        config: HarpyConfig | None = None,
        prefs: PrefsStore | None = None,
        review_id: UUID | None = None,
        store_root: Path | None = None,
    ) -> None:
        super().__init__()
        self.result = result
        self.config = config
        self.review_id = review_id
        self.store_root = store_root
        self.workspace = workspace_from_result(result)
        if review_id is not None:
            session = load_review_session(review_id, root=store_root)
            if session is not None:
                apply_session(self.workspace, session, result)
        self.selected_id: str | None = self.workspace.selected_id
        self.selected_file: str | None = self.workspace.selected_file
        self.expanded = False
        self.hide_noise = False
        self.api_mode = False
        self.api_index = 0
        self.api_file: str | None = None
        self._impact_zoom_pane: str | None = None
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
        self._active_run = 0
        self._workspace_ready = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="freshness")
        yield Input(
            placeholder="Search titles, paths, symbols, questions, notes…", id="search-input"
        )
        yield ApiList(id="api-list")
        yield ChangeList(id="changes")
        yield ApiDiagramView(id="api-diagram")
        yield DiffView(id="diff")
        yield ApiDetail(id="api-detail")
        yield ContextPanel(id="context")
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).display = False
        self._set_api_visible(False)
        self._workspace_ready = True
        self._refresh()
        if self.workspace.lens == "impact" and entries_from_result(self.result):
            self.action_api_view()
        elif self.workspace.focused_pane == "canvas":
            self.query_one(DiffView).focus()
        elif self.workspace.focused_pane == "inspector":
            self.query_one(ContextPanel).focus()
        else:
            self.query_one(ChangeList).focus()

    def on_unmount(self) -> None:
        self._persist_context()

    def _persist_context(self) -> None:
        if self.review_id is None:
            return
        self.workspace.selected_id = self.selected_id
        self.workspace.selected_file = self.selected_file
        save_review_session(
            session_from_workspace(self.review_id, self.workspace, self.result),
            root=self.store_root,
        )

    def on_resize(self) -> None:
        if self._workspace_ready:
            self._apply_pane_visibility()

    def _tick_progress(self) -> None:
        if not self._semantic_running:
            return
        self._progress_i = (self._progress_i + 1) % 3
        self.query_one(StatusBar).set_text(f"{self._progress_label}{'.' * (self._progress_i + 1)}")

    def _set_progress(self, message: str) -> None:
        self._progress_label = message
        self.query_one(StatusBar).set_text(message)

    def _entering_text(self) -> bool:
        return self.workspace.entering_text or isinstance(self.focused, Input)

    def action_scope(self) -> None:
        if self._entering_text() or not self._semantic_allowed or self.config is None:
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
        self._active_run += 1
        run_id = self._active_run
        self.result.pending_semantic = True
        self._progress_label = "Analyzing semantic changes"
        self.set_interval(0.5, self._tick_progress)
        self.run_worker(lambda: self._run_semantic(run_id), exclusive=True, thread=True)

    def _run_semantic(self, run_id: int) -> None:
        from harpy.analysis.pipeline import apply_semantic

        assert self.config is not None

        def progress(message: str) -> None:
            if run_id != self._active_run:
                return
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
            if run_id != self._active_run:
                return
            failed = self.result.model_copy(deep=True)
            failed.pending_semantic = False
            failed.banner = (
                f"Semantic analysis unavailable. Showing static review priority only. ({exc})"
            )
            updated = failed
        self.call_from_thread(self._apply_updated, updated, run_id)

    def _apply_updated(self, updated: AnalysisResult, run_id: int) -> None:
        if run_id != self._active_run:
            return
        focused_id = self.focused.id if self.focused is not None else None
        self._semantic_running = False
        self.result = updated
        visible = self._visible()
        if self.selected_id not in {change.id for change in visible}:
            self.selected_id = visible[0].id if visible else None
            self.selected_file = None
            self.workspace.selected_id = self.selected_id
            self.workspace.selected_file = None
        self._refresh()
        if focused_id is not None:
            try:
                self.query_one(f"#{focused_id}").focus()
            except Exception:  # noqa: BLE001
                pass

    def _visible(self) -> list[LogicalChange]:
        changes = self.result.changes
        if self.hide_noise:
            changes = [
                item for item in changes if item.risk not in {"LOW"} or item.importance >= 20
            ]
        return search_changes(changes, self.workspace.search, self.workspace.notes)

    def _current(self) -> LogicalChange | None:
        visible = self._visible()
        by_id = {change.id: change for change in visible}
        if self.selected_id in by_id:
            return by_id[self.selected_id]
        if not visible:
            self.selected_id = None
            self.workspace.selected_id = None
            return None
        self.selected_id = visible[0].id
        self.workspace.selected_id = self.selected_id
        return visible[0]

    def _freshness_banner(self) -> str | None:
        header = self.workspace.header()
        parts = [header.badge]
        if self.result.banner:
            parts.append(self.result.banner)
        return " · ".join(parts)

    def _status_text(self) -> str:
        header = self.workspace.header()
        reviewed, total = review_progress(self.result.changes, self.workspace.statuses)
        covered, hunks = coverage_progress(self.result)
        progress = f"{header.badge}  ·  review {reviewed}/{total}  ·  coverage {covered}/{hunks}"
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
            return f"{progress}  ·  {_impact_status(self.result)}  ·  {hint}"
        focused = self.focused.id if self.focused is not None else "changes"
        hint = {
            "changes": "j/k move  space fold  i impact  s scope  tab pane",
            "diff": "j/k scroll  n/p this context  tab pane",
            "context": "j/k scroll context  tab pane",
        }.get(focused or "", "tab pane")
        if self.workspace.search:
            hint = f"/{self.workspace.search}  ·  {hint}"
        if self.result.banner:
            return f"{progress}  ·  {self.result.banner}  ·  {hint}"
        if self.result.semantic_available:
            return f"{progress}  ·  Semantic analysis ready  ·  {hint}"
        if self._semantic_running:
            return f"{progress}  ·  {self._progress_label}  ·  {hint}"
        if self._semantic_allowed:
            return f"{progress}  ·  Semantic analysis not started  ·  s scope  ·  {hint}"
        return f"{progress}  ·  Static review priority only.  ·  {hint}"

    def on_change_list_cursor_moved(self, event: ChangeList.CursorMoved) -> None:
        if event.change_id is None:
            return
        if event.change_id == self.selected_id and event.file_path == self.selected_file:
            return
        self.workspace.select(event.change_id, event.file_path)
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

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search-input":
            return
        self.workspace.search = event.value
        self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search-input":
            return
        self._finish_search()

    def _impact_panes(self) -> tuple[str, ...]:
        if self.api_file:
            return _API_FILE_PANES
        return _API_PANES

    def _pane_displayed(self, pane_id: str) -> bool:
        return bool(self.query_one(f"#{pane_id}").display)

    def _active_panes(self) -> tuple[str, ...]:
        candidates = self._impact_panes() if self.api_mode else self._visible_review_panes()
        visible = tuple(pane_id for pane_id in candidates if self._pane_displayed(pane_id))
        return visible or candidates

    def action_focus_next_pane(self) -> None:
        if self.api_mode and self.workspace.maximized:
            panes = self._impact_panes()
        else:
            panes = self._active_panes()
        if not panes:
            return
        current = self.focused.id if self.focused is not None else panes[0]
        try:
            index = panes.index(current)
        except ValueError:
            index = -1
        next_id = panes[(index + 1) % len(panes)]
        if self.api_mode and self.workspace.maximized:
            self._impact_zoom_pane = next_id
            self._apply_pane_visibility()
        self.query_one(f"#{next_id}").focus()
        region = _PANE_TO_REGION.get(next_id)
        if region is not None:
            self.workspace.focused_pane = region
            if region == "inspector":
                self.workspace.inspector_open = True
        if not self.api_mode:
            self._apply_pane_visibility()
        self.query_one(StatusBar).set_text(self._status_text())

    def action_api_view(self) -> None:
        if self._entering_text():
            return
        if self.api_mode:
            self.api_mode = False
            self.workspace.maximized = False
            self._impact_zoom_pane = None
            self.workspace.set_lens("overview")
            self._set_api_visible(False)
            self.query_one(ChangeList).focus()
            self._show_panes()
            return
        if not entries_from_result(self.result):
            self.notify("No endpoint or database contract changes")
            return
        selected = self.selected_id
        self.workspace.set_lens("impact")
        self.workspace.selected_id = selected
        self.workspace.maximized = False
        self._impact_zoom_pane = None
        self.api_mode = True
        self.api_index = 0
        self.api_file = None
        self._set_api_visible(True)
        self.query_one(ApiList).populate(entries_from_result(self.result), selected=0)
        self.query_one(ApiList).focus()
        self._show_api()

    def action_leave_api(self) -> None:
        if self.workspace.entering_text:
            self._close_search()
            return
        if self.workspace.maximized:
            self.workspace.maximized = False
            self._apply_pane_visibility()
            return
        if self.api_mode:
            self.action_api_view()
            return
        layout = workspace_layout(self.size.width, self.size.height)
        if layout.inspector_drawer and self.workspace.inspector_open:
            self.workspace.inspector_open = False
            self.workspace.focused_pane = "navigator"
            self.query_one(ChangeList).focus()
            self._apply_pane_visibility()
            return
        self.action_nav_back()

    def _set_api_visible(self, visible: bool) -> None:
        self.screen.set_class(visible, "-impact")
        for pane_id in _REVIEW_PANES:
            self.query_one(f"#{pane_id}").display = not visible
        for pane_id in _API_PANES:
            self.query_one(f"#{pane_id}").display = visible
        self.query_one("#freshness").display = True

    def _refresh(self) -> None:
        self._paint_freshness()
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
        status = (
            self.workspace.statuses.get(current.id, ReviewStatus.UNREVIEWED)
            if current
            else ReviewStatus.UNREVIEWED
        )
        self.query_one(ContextPanel).show(
            current,
            banner=self._freshness_banner(),
            status=status,
            text=lens_inspector(
                current,
                lens=self.workspace.lens,
                status=status,
                banner=self._freshness_banner(),
                notes=self.workspace.notes,
                history=self.workspace.history,
                head_sha=self.result.pr.head_sha,
            ),
            head_sha=self.result.pr.head_sha,
        )
        self._apply_pane_visibility()
        self.query_one(StatusBar).set_text(self._status_text())

    def _show_api(self) -> None:
        items = entries_from_result(self.result)
        item = items[self.api_index] if items and 0 <= self.api_index < len(items) else None
        file_path = self.api_file if item is not None else None
        showing_diff = bool(file_path)
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
        self._apply_pane_visibility()
        self._paint_freshness()
        self.query_one(StatusBar).set_text(self._status_text())

    def _paint_freshness(self) -> None:
        header = self.workspace.header()
        notice = (
            "  ·  compact layout"
            if workspace_layout(self.size.width, self.size.height).compact_notice
            else ""
        )
        self.query_one("#freshness", Static).update(
            f"{header.analyzed}  ·  {header.latest}  ·  {header.badge}{notice}"
        )

    def _visible_review_panes(self) -> tuple[str, ...]:
        layout = workspace_layout(self.size.width, self.size.height)
        self.workspace.apply_layout(layout)
        if self.workspace.maximized:
            return (_REGION_TO_PANE.get(self.workspace.focused_pane, "changes"),)
        regions = self.workspace.visible_panes(layout)
        return tuple(_REGION_TO_PANE[region] for region in regions if region in _REGION_TO_PANE)

    def _apply_impact_visibility(self) -> None:
        showing_diff = bool(self.api_file)
        trio = ("api-list", "diff" if showing_diff else "api-diagram", "api-detail")
        hidden = ("changes", "context", "diff" if not showing_diff else "api-diagram")
        if self.workspace.maximized:
            target = self._impact_zoom_pane
            if target not in trio:
                focused = self.focused.id if self.focused is not None else None
                target = focused if focused in trio else trio[0]
                self._impact_zoom_pane = target
            for pane_id in (*_API_PANES, "diff", "changes", "context"):
                self.query_one(f"#{pane_id}").display = pane_id == target
            return
        for pane_id in trio:
            self.query_one(f"#{pane_id}").display = True
        for pane_id in hidden:
            self.query_one(f"#{pane_id}").display = False

    def _apply_pane_visibility(self) -> None:
        layout = workspace_layout(self.size.width, self.size.height)
        self.workspace.apply_layout(layout)
        self.screen.set_class(not layout.single_pane and not layout.inspector_drawer, "-wide")
        self.screen.set_class(layout.inspector_drawer, "-mid")
        self.screen.set_class(layout.single_pane, "-narrow")
        self.screen.set_class(layout.compact_notice, "-compact")
        self.screen.set_class(self.workspace.maximized, "-zoomed")
        if self.api_mode:
            self._apply_impact_visibility()
            return
        visible = set(self._visible_review_panes())
        for pane_id in _REVIEW_PANES:
            self.query_one(f"#{pane_id}").display = pane_id in visible
        for pane_id in _API_PANES:
            self.query_one(f"#{pane_id}").display = False

    def _set_lens(self, lens: str) -> None:
        if self._entering_text():
            return
        if self.api_mode and lens != "impact":
            self.api_mode = False
            self.workspace.maximized = False
            self._impact_zoom_pane = None
            self._set_api_visible(False)
        selected = self.selected_id
        selected_file = self.selected_file
        self.workspace.set_lens(lens)
        self.workspace.selected_id = selected
        self.workspace.selected_file = selected_file
        if lens == "diff":
            self.workspace.focused_pane = "canvas"
            self.workspace.inspector_open = True
            self.query_one(DiffView).focus()
        elif lens == "impact":
            self.action_api_view()
            return
        else:
            self.workspace.focused_pane = "inspector"
            self.workspace.inspector_open = True
            self.query_one(ContextPanel).focus()
        self._show_panes()

    def action_expand(self) -> None:
        if self._entering_text() or self.api_mode:
            return
        self.expanded = not self.expanded
        self._show_panes()

    def action_collapse(self) -> None:
        if self._entering_text() or self.api_mode:
            return
        self.hide_noise = not self.hide_noise
        self.selected_id = None
        self.selected_file = None
        self.workspace.selected_id = None
        self.workspace.selected_file = None
        self._refresh()

    def action_all(self) -> None:
        if self._entering_text() or self.api_mode:
            return
        self.hide_noise = False
        self._refresh()

    def action_questions(self) -> None:
        self._set_lens("questions")

    def action_tests(self) -> None:
        self._set_lens("tests")

    def action_omissions(self) -> None:
        self._set_lens("omissions")

    def action_search(self) -> None:
        if self.api_mode:
            return
        box = self.query_one("#search-input", Input)
        box.display = True
        self.workspace.entering_text = True
        box.focus()

    def _finish_search(self) -> None:
        self.workspace.entering_text = False
        self.query_one("#search-input", Input).display = False
        self.query_one(ChangeList).focus()
        self._refresh()

    def _close_search(self) -> None:
        self.workspace.search = ""
        self.query_one("#search-input", Input).value = ""
        self._finish_search()

    def action_palette(self) -> None:
        if self._entering_text():
            return
        self.push_screen(CommandPalette(), self._palette_chosen)

    def _palette_chosen(self, action_id: str | None) -> None:
        if not action_id or action_id == "palette":
            return
        actions = {
            "scope": self.action_scope,
            "expand": self.action_expand,
            "impact": self.action_api_view,
            "questions": self.action_questions,
            "tests": self.action_tests,
            "omissions": self.action_omissions,
            "search": self.action_search,
            "help": self.action_help,
            "collapse": self.action_collapse,
            "all": self.action_all,
            "zoom": self.action_zoom,
            "reviewed": self.action_reviewed,
            "reopen": self.action_reopen,
            "blocker": self.action_blocker,
            "note": self.action_note,
            "back": self.action_leave_api,
            "quit": self.action_quit,
        }
        action = actions.get(action_id)
        if action is not None:
            action()

    def action_help(self) -> None:
        if self._entering_text():
            return
        self.push_screen(HelpScreen())

    def action_zoom(self) -> None:
        if self._entering_text():
            return
        focused = self.focused.id if self.focused is not None else None
        if self.api_mode:
            panes = self._active_panes() or self._impact_panes()
            target = focused if focused in panes else panes[0]
            self.workspace.maximized = not self.workspace.maximized
            self._impact_zoom_pane = target if self.workspace.maximized else None
            self._apply_pane_visibility()
            self.query_one(f"#{target}").focus()
            self.query_one(StatusBar).set_text(self._status_text())
            return
        region = _PANE_TO_REGION.get(focused or "")
        if region is not None:
            self.workspace.focused_pane = region
        self.workspace.maximized = not self.workspace.maximized
        self._apply_pane_visibility()
        pane_id = _REGION_TO_PANE.get(self.workspace.focused_pane, "changes")
        self.query_one(f"#{pane_id}").focus()
        self.query_one(StatusBar).set_text(self._status_text())

    def action_reviewed(self) -> None:
        if self._entering_text():
            return
        self.workspace.selected_id = self.selected_id
        self.workspace.mark(ReviewStatus.REVIEWED)
        self._persist_context()
        self._show_panes()

    def action_reopen(self) -> None:
        if self._entering_text():
            return
        self.workspace.selected_id = self.selected_id
        self.workspace.mark(ReviewStatus.UNREVIEWED)
        self._persist_context()
        self._show_panes()

    def action_blocker(self) -> None:
        if self._entering_text():
            return
        self.workspace.selected_id = self.selected_id
        self.workspace.mark(ReviewStatus.BLOCKER)
        self._persist_context()
        self._show_panes()

    def action_note(self) -> None:
        if self._entering_text():
            return
        self.workspace.entering_text = True
        self.push_screen(NoteDialog(), self._note_chosen)

    def _note_chosen(self, text: str | None) -> None:
        self.workspace.entering_text = False
        if text:
            self.workspace.selected_id = self.selected_id
            self.workspace.add_note(text)
            self._persist_context()
            self._show_panes()

    def action_nav_back(self) -> None:
        if self._entering_text():
            return
        anchor = self.workspace.back()
        if anchor is None:
            return
        self.selected_id = anchor.change_id
        self.selected_file = anchor.file_path
        self._restore_anchor()

    def action_nav_forward(self) -> None:
        if self._entering_text():
            return
        anchor = self.workspace.forward()
        if anchor is None:
            return
        self.selected_id = anchor.change_id
        self.selected_file = anchor.file_path
        self._restore_anchor()

    def _restore_anchor(self) -> None:
        if self.workspace.lens == "impact":
            if not self.api_mode:
                self.action_api_view()
            return
        if self.api_mode:
            self.api_mode = False
            self._set_api_visible(False)
        self._refresh()


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
    review_id: UUID | None = None,
    store_root: Path | None = None,
) -> None:
    HarpyApp(result, config=config, prefs=prefs, review_id=review_id, store_root=store_root).run()
