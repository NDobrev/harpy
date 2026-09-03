from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from harpy.tui.impact_entries import (
    ImpactDisplayRow,
    ImpactEntry,
    row_classes,
    rows_from_entries,
    visible_impact_rows,
)


class ApiList(VerticalScroll):
    BINDINGS = [
        *VerticalScroll.BINDINGS,
        Binding("j", "cursor_down", "Next", show=False),
        Binding("k", "cursor_up", "Prev", show=False),
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("space", "toggle_fold", "Fold"),
        Binding("h,left", "fold", show=False),
        Binding("l,right", "unfold", show=False),
    ]
    can_focus_children = False

    class CursorMoved(Message):
        def __init__(self, index: int, file_path: str | None = None) -> None:
            super().__init__()
            self.index = index
            self.file_path = file_path

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._items: list[ImpactEntry] = []
        self._rows: list[ImpactDisplayRow] = []
        self._visible: list[ImpactDisplayRow] = []
        self._collapsed: set[str] = set()
        self._cursor = 0

    def populate(
        self,
        items: list[ImpactEntry],
        selected: int = 0,
        selected_file: str | None = None,
    ) -> None:
        self._items = items
        self._rows = rows_from_entries(items)
        self._collapsed &= {row.node_key for row in self._rows if row.has_children}
        self._visible = visible_impact_rows(self._rows, self._collapsed)
        self._cursor = _cursor_for(self._visible, selected, selected_file)
        self._remount()
        self._paint()

    def current(self) -> ImpactEntry | None:
        if not self._items:
            return None
        row = self._current_row()
        if row is None:
            return None
        return self._items[row.impact_index]

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def action_toggle_fold(self) -> None:
        row = self._fold_target()
        if row is None or not row.node_key:
            return
        if row.node_key in self._collapsed:
            self._collapsed.discard(row.node_key)
        else:
            self._collapsed.add(row.node_key)
        self._relayout()

    def action_fold(self) -> None:
        row = self._fold_target()
        if row is None or not row.node_key:
            return
        self._collapsed.add(row.node_key)
        self._relayout()

    def action_unfold(self) -> None:
        row = self._fold_target()
        if row is None or not row.node_key:
            return
        self._collapsed.discard(row.node_key)
        self._relayout()

    def _fold_target(self) -> ImpactDisplayRow | None:
        row = self._current_row()
        if row is None:
            return None
        if row.has_children:
            return row
        if row.parent_key:
            for item in self._rows:
                if item.node_key == row.parent_key:
                    return item
        return row

    def _relayout(self) -> None:
        current = self._current_row()
        self._visible = visible_impact_rows(self._rows, self._collapsed)
        if current is not None:
            for index, row in enumerate(self._visible):
                if row.kind == current.kind and row.impact_index == current.impact_index:
                    if current.file_path is None or row.file_path == current.file_path:
                        self._cursor = index
                        break
            else:
                self._cursor = _cursor_for(self._visible, current.impact_index)
        self._cursor = max(0, min(self._cursor, max(len(self._visible) - 1, 0)))
        self._remount()
        self._paint()
        self._notify()

    def _move(self, delta: int) -> None:
        if not self._visible:
            return
        self._cursor = max(0, min(self._cursor + delta, len(self._visible) - 1))
        self._paint()
        self._notify()

    def _current_row(self) -> ImpactDisplayRow | None:
        if not self._visible:
            return None
        return self._visible[self._cursor]

    def _notify(self) -> None:
        row = self._current_row()
        if row is None:
            return
        self.post_message(self.CursorMoved(row.impact_index, row.file_path))

    def _remount(self) -> None:
        self.remove_children()
        widgets = [
            Static(
                row.render(collapsed=row.node_key in self._collapsed),
                classes=row_classes(row),
                markup=True,
            )
            for row in self._visible
        ]
        if widgets:
            self.mount(*widgets)

    def _paint(self) -> None:
        children = list(self.query(Static))
        for index, child in enumerate(children):
            child.set_class(index == self._cursor, "-selected")
        if 0 <= self._cursor < len(children):
            self.scroll_to_widget(children[self._cursor], animate=False)


def _cursor_for(
    rows: list[ImpactDisplayRow],
    impact_index: int,
    file_path: str | None = None,
) -> int:
    if file_path:
        for index, row in enumerate(rows):
            if row.impact_index == impact_index and row.file_path == file_path:
                return index
    for index, row in enumerate(rows):
        if row.kind == "impact" and row.impact_index == impact_index:
            return index
    return 0
