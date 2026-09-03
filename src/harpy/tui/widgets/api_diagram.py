from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from harpy.analysis.diagrams.render import paint_rendered, render_pictures, wrap_index
from harpy.analysis.schema_view import merge_snapshots
from harpy.models import DbChangeImpact, RenderedDiagram, SchemaSnapshot
from harpy.tui.impact_entries import ImpactEntry

_EMPTY = (
    "No diagram.\n"
    "The analyzer only draws one when old/new flow or a sequence would otherwise be easy to miss."
)
_EMPTY_SCHEMA = (
    "No schema picture yet.\n"
    "Static ranking lists the table; semantic analysis fills columns and relations."
)


class ApiDiagramView(VerticalScroll):
    BINDINGS = [
        *VerticalScroll.BINDINGS,
        Binding("j", "hit_next", show=False),
        Binding("k", "hit_prev", show=False),
        Binding("J", "scroll_down", show=False),
        Binding("K", "scroll_up", show=False),
        Binding("]", "next_picture", show=False),
        Binding("[", "prev_picture", show=False),
        Binding("enter", "open_hit", show=False),
    ]
    can_focus_children = False

    class NodeSelected(Message):
        def __init__(self, path: str, line: int = 0) -> None:
            super().__init__()
            self.path = path
            self.line = line

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._pictures: list[RenderedDiagram] = []
        self._pic_index = 0
        self._hit_index = 0

    def compose(self) -> ComposeResult:
        yield Static(id="api-diagram-body", shrink=True, markup=True)

    def show(
        self,
        item: ImpactEntry | None,
        *,
        db_impacts: list[DbChangeImpact] | None = None,
    ) -> None:
        self._pictures = []
        self._pic_index = 0
        self._hit_index = 0
        if item is None:
            self._paint_text("")
            return
        schema = SchemaSnapshot()
        highlight = ""
        sequence = None
        flow = None
        tree = None
        if item.db is not None:
            snapshots = [impact.schema_snapshot for impact in (db_impacts or [item.db])]
            schema = merge_snapshots(snapshots)
            highlight = item.db.target
            sequence = item.db.sequence
            flow = item.db.flow
            tree = item.db.tree
        elif item.api is not None:
            sequence = item.api.sequence
            flow = item.api.flow
            tree = item.api.tree
        self._pictures = render_pictures(
            schema=schema,
            diagrams=item.diagrams,
            sequence=sequence,
            flow=flow,
            tree=tree,
            highlight=highlight,
        )
        if self._pictures:
            self._paint()
            return
        if item.db is not None:
            self._paint_text(_EMPTY_SCHEMA)
            return
        if item.diagrams:
            parts: list[str] = []
            for diagram in item.diagrams:
                parts.extend(
                    [
                        diagram.title or diagram.kind,
                        "",
                        f"why: {diagram.why}" if diagram.why else "",
                        "",
                    ]
                )
            self._paint_text("\n".join(part for part in parts if part))
            return
        self._paint_text(_EMPTY)

    def current_picture(self) -> RenderedDiagram | None:
        if not self._pictures:
            return None
        return self._pictures[self._pic_index]

    def status_hint(self) -> str:
        picture = self.current_picture()
        if picture is None:
            return "j/k scroll schema  tab pane"
        count = len(self._pictures)
        return (
            f"{picture.kind} {self._pic_index + 1}/{count}  "
            "[/] picture  j/k node  enter open file  tab pane"
        )

    def action_hit_next(self) -> None:
        self._move_hit(1)

    def action_hit_prev(self) -> None:
        self._move_hit(-1)

    def action_next_picture(self) -> None:
        self._move_picture(1)

    def action_prev_picture(self) -> None:
        self._move_picture(-1)

    def action_open_hit(self) -> None:
        picture = self.current_picture()
        if picture is None or not picture.hits:
            return
        hit = picture.hits[self._hit_index]
        if not hit.path:
            return
        self.post_message(self.NodeSelected(hit.path, hit.line))

    def _move_hit(self, delta: int) -> None:
        picture = self.current_picture()
        if picture is None or not picture.hits:
            if delta > 0:
                self.action_scroll_down()
            else:
                self.action_scroll_up()
            return
        self._hit_index = wrap_index(self._hit_index, len(picture.hits), delta)
        self._paint()

    def _move_picture(self, delta: int) -> None:
        if not self._pictures:
            return
        self._pic_index = wrap_index(self._pic_index, len(self._pictures), delta)
        self._hit_index = 0
        self._paint()

    def _paint(self) -> None:
        picture = self.current_picture()
        if picture is None:
            self._paint_text("")
            return
        header = picture.title or picture.kind
        body = paint_rendered(picture, self._hit_index)
        if header and not (picture.lines and picture.lines[0] == header):
            body = f"{header}\n{body}"
        self._paint_text(body)

    def _paint_text(self, text: str) -> None:
        self.query_one("#api-diagram-body", Static).update(text)
