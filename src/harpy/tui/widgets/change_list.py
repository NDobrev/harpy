from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from harpy.models import DiffHunk, LogicalChange
from harpy.tui.change_tree import (
    DisplayRow,
    build_change_forest,
    flatten_forest,
    visible_rows,
)


def change_label(change: LogicalChange, *, selected: bool = False) -> str:
    mark = {"CRITICAL": "🔴", "HIGH": "🔴", "MEDIUM": "🟠", "LOW": "⚪"}.get(change.risk, "🟡")
    extra = ""
    if change.unexpectedness > 70:
        extra += " !"
    if change.confidence < 0.6:
        extra += " ?"
    cursor = "▸ " if selected else "  "
    return f"{cursor}{change.review_priority:3.0f} {mark} {change.risk:8} {change.title}{extra}"


class ChangeList(VerticalScroll):
    BINDINGS = [
        *VerticalScroll.BINDINGS,
        Binding("j", "cursor_down", "Next", show=False),
        Binding("k", "cursor_up", "Prev", show=False),
        Binding("up", "cursor_up", "Prev", show=False),
        Binding("down", "cursor_down", "Next", show=False),
        Binding("space", "toggle_fold", "Fold"),
        Binding("h,left", "fold", "Fold", show=False),
        Binding("l,right", "unfold", "Unfold", show=False),
    ]
    can_focus_children = False

    class CursorMoved(Message):
        def __init__(self, change_id: str | None, file_path: str | None) -> None:
            super().__init__()
            self.change_id = change_id
            self.file_path = file_path

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._rows: list[DisplayRow] = []
        self._visible: list[DisplayRow] = []
        self._signature: tuple[tuple[str, str | None, str | None], ...] = ()
        self._collapsed: set[str] = set()
        self._cursor = 0

    def populate(
        self,
        changes: list[LogicalChange],
        *,
        hunks: list[DiffHunk],
        selected_id: str | None,
        selected_file: str | None,
    ) -> None:
        rows = flatten_forest(build_change_forest(changes), hunks)
        signature = tuple((row.kind, row.change_id, row.file_path) for row in rows)
        if signature != self._signature:
            first_population = not self._signature
            self._signature = signature
            self._rows = rows
            valid_keys = {row.node_key for row in rows if row.node_key}
            if first_population:
                self._collapsed = {
                    row.node_key
                    for row in rows
                    if row.kind == "change" and row.has_children and row.node_key
                }
            else:
                self._collapsed &= valid_keys
            self._remount()
        self.set_cursor(selected_id, selected_file, notify=False)

    def set_cursor(
        self,
        change_id: str | None,
        file_path: str | None,
        *,
        notify: bool = True,
    ) -> None:
        index = _index_of(self._visible, change_id, file_path)
        if index is None:
            index = next((i for i, row in enumerate(self._visible) if row.selectable), None)
        if index is None:
            return
        self._cursor = index
        self._paint_cursor()
        row = self._visible[index]
        if notify:
            self.post_message(self.CursorMoved(row.change_id, row.file_path))

    def current(self) -> DisplayRow | None:
        if not self._visible or not (0 <= self._cursor < len(self._visible)):
            return None
        return self._visible[self._cursor]

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def action_toggle_fold(self) -> None:
        self._fold(toggle=True)

    def action_fold(self) -> None:
        self._fold(toggle=False, collapse=True)

    def action_unfold(self) -> None:
        self._fold(toggle=False, collapse=False)

    def _fold(self, *, toggle: bool, collapse: bool = True) -> None:
        row = self.current()
        if row is None:
            return
        key = row.node_key if row.has_children else row.parent_key
        if not key:
            return
        if toggle:
            if key in self._collapsed:
                self._collapsed.discard(key)
            else:
                self._collapsed.add(key)
        elif collapse:
            self._collapsed.add(key)
        else:
            self._collapsed.discard(key)
        selected = (row.change_id, row.file_path)
        if key in self._collapsed and not row.has_children:
            parent = next((item for item in self._rows if item.node_key == key), None)
            if parent is not None:
                selected = (parent.change_id, parent.file_path)
        self._remount()
        self.set_cursor(selected[0], selected[1], notify=True)

    def _remount(self) -> None:
        self._visible = visible_rows(self._rows, self._collapsed)
        self.remove_children()
        widgets = [
            Static(
                row.render(collapsed=bool(row.node_key and row.node_key in self._collapsed)),
                classes=_row_classes(row),
                markup=False,
            )
            for row in self._visible
        ]
        if widgets:
            self.mount(*widgets)

    def _move(self, delta: int) -> None:
        selectable = [index for index, row in enumerate(self._visible) if row.selectable]
        if not selectable:
            return
        if self._cursor not in selectable:
            self._cursor = selectable[0]
        position = selectable.index(self._cursor)
        self._cursor = selectable[max(0, min(position + delta, len(selectable) - 1))]
        self._paint_cursor()
        row = self._visible[self._cursor]
        self.post_message(self.CursorMoved(row.change_id, row.file_path))

    def _paint_cursor(self) -> None:
        children = list(self.query(Static))
        for index, child in enumerate(children):
            child.set_class(index == self._cursor, "-selected")
        if 0 <= self._cursor < len(children):
            self.scroll_to_widget(children[self._cursor], animate=False)


def _row_classes(row: DisplayRow) -> str:
    classes = f"tree-row tree-{row.kind}"
    if row.selectable:
        classes += " tree-selectable"
    return classes


def _index_of(rows: list[DisplayRow], change_id: str | None, file_path: str | None) -> int | None:
    for index, row in enumerate(rows):
        if row.change_id == change_id and row.file_path == file_path:
            return index
    if change_id is None:
        return None
    for index, row in enumerate(rows):
        if row.kind == "change" and row.change_id == change_id:
            return index
    return None
