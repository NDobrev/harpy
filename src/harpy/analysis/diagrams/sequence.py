"""ASCII sequence diagrams with actor lifelines."""

from __future__ import annotations

from harpy.models import DiagramHit, RenderedDiagram, SequenceDiagram, SequenceStep

_MIN_COL = 12
_CHANGE = {"add": "+", "drop": "-", "alter": "~"}


def render_sequence_diagram(diagram: SequenceDiagram) -> RenderedDiagram:
    actors = _actors(diagram)
    if not actors:
        return RenderedDiagram(kind="sequence", title="SEQUENCE")
    widths = [_column_width(actor, diagram.steps, actors) for actor in actors]
    offsets = _offsets(widths)
    centers = [offset + width // 2 for offset, width in zip(offsets, widths, strict=True)]
    total = sum(widths)
    lines: list[str] = ["SEQUENCE", ""]
    hits: list[DiagramHit] = []
    header = [" "] * total
    for actor, offset, width in zip(actors, offsets, widths, strict=True):
        _place(header, offset + max(0, (width - len(actor)) // 2), actor)
        hits.append(
            DiagramHit(
                row=len(lines),
                col=offset + max(0, (width - len(actor)) // 2),
                width=len(actor),
                node_id=f"actor:{actor}",
            )
        )
    lines.append("".join(header).rstrip())
    lines.append(_join(_lifelines(centers, total)))
    for index, step in enumerate(diagram.steps):
        src = _center_of(step.from_actor, actors, centers)
        dest = _center_of(step.to_actor, actors, centers)
        if src is None or dest is None or src == dest:
            continue
        message = _message(step)
        msg_row = _lifelines(centers, total)
        lo, hi = min(src, dest), max(src, dest)
        span = max(1, hi - lo - 1)
        shown = message[:span]
        start = lo + 1 + max(0, (span - len(shown)) // 2)
        _place(msg_row, start, shown)
        lines.append(_join(msg_row))
        if shown:
            hits.append(
                DiagramHit(
                    row=len(lines) - 1,
                    col=start,
                    width=len(shown),
                    node_id=f"step:{index}",
                    path=step.path,
                )
            )
        arrow = _lifelines(centers, total)
        if src < dest:
            for col in range(src + 1, dest):
                arrow[col] = "─"
            arrow[dest] = "►"
        else:
            arrow[dest] = "◄"
            for col in range(dest + 1, src):
                arrow[col] = "─"
        lines.append(_join(arrow))
        lines.append(_join(_lifelines(centers, total)))
    return RenderedDiagram(title="SEQUENCE", kind="sequence", lines=lines, hits=hits)


def _actors(diagram: SequenceDiagram) -> list[str]:
    actors = [name for name in diagram.actors if name]
    for step in diagram.steps:
        for name in (step.from_actor, step.to_actor):
            if name and name not in actors:
                actors.append(name)
    return actors


def _column_width(actor: str, steps: list[SequenceStep], actors: list[str]) -> int:
    width = max(_MIN_COL, len(actor) + 2)
    index = actors.index(actor)
    for step in steps:
        try:
            src = actors.index(step.from_actor)
            dest = actors.index(step.to_actor)
        except ValueError:
            continue
        if min(src, dest) != index:
            continue
        span = abs(dest - src)
        if span <= 0:
            continue
        needed = (len(_message(step)) + 2 + span) // span
        width = max(width, needed)
    return width


def _message(step: SequenceStep) -> str:
    mark = _CHANGE.get(step.change, "")
    if mark:
        return f"{step.message} {mark}".strip()
    return step.message


def _offsets(widths: list[int]) -> list[int]:
    offsets: list[int] = []
    pos = 0
    for width in widths:
        offsets.append(pos)
        pos += width
    return offsets


def _center_of(name: str, actors: list[str], centers: list[int]) -> int | None:
    try:
        return centers[actors.index(name)]
    except ValueError:
        return None


def _lifelines(centers: list[int], total: int) -> list[str]:
    cells = [" "] * total
    for center in centers:
        if 0 <= center < total:
            cells[center] = "│"
    return cells


def _place(cells: list[str], start: int, text: str) -> None:
    for offset, char in enumerate(text):
        index = start + offset
        if 0 <= index < len(cells):
            cells[index] = char


def _join(cells: list[str]) -> str:
    return "".join(cells).rstrip()
