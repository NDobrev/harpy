"""Dispatch structured diagrams (and mermaid fallback) to ASCII pictures."""

from __future__ import annotations

from rich.markup import escape

from harpy.analysis.diagrams.flow import render_flow_diagram
from harpy.analysis.diagrams.mermaid import (
    classify_mermaid,
    parse_er_mermaid,
    parse_flowchart_mermaid,
    parse_sequence_mermaid,
)
from harpy.analysis.diagrams.schema import schema_picture
from harpy.analysis.diagrams.sequence import render_sequence_diagram
from harpy.analysis.diagrams.tree import render_blast_tree
from harpy.models import (
    ApiDiagram,
    BlastTree,
    DiagramHit,
    FlowDiagram,
    RenderedDiagram,
    SchemaSnapshot,
    SequenceDiagram,
)


def render_pictures(
    *,
    schema: SchemaSnapshot,
    diagrams: list[ApiDiagram],
    sequence: SequenceDiagram | None = None,
    flow: FlowDiagram | None = None,
    tree: BlastTree | None = None,
    highlight: str = "",
    width: int = 40,
) -> list[RenderedDiagram]:
    pictures: list[RenderedDiagram] = []
    if schema.tables:
        pictures.append(schema_picture(schema, highlight=highlight, width=width))
    seen_seq = False
    seen_flow = False
    seen_tree = False
    top_seq = sequence if sequence is not None and sequence.steps else None
    top_flow = flow if flow is not None and (flow.nodes or flow.edges) else None
    if top_seq is not None:
        pictures.append(render_sequence_diagram(top_seq))
        seen_seq = True
    if top_flow is not None:
        pictures.append(render_flow_diagram(top_flow))
        seen_flow = True
    for diagram in diagrams:
        seq = _sequence_of(diagram)
        if seq is not None and not seen_seq:
            pictures.append(render_sequence_diagram(seq))
            seen_seq = True
        parsed_flow = _flow_of(diagram)
        if parsed_flow is not None and not seen_flow:
            pictures.append(render_flow_diagram(parsed_flow))
            seen_flow = True
        if not schema.tables:
            parsed_schema = _schema_of(diagram)
            if parsed_schema is not None and parsed_schema.tables:
                pictures.append(schema_picture(parsed_schema, highlight=highlight, width=width))
        if diagram.tree is not None and diagram.tree.root.children and not seen_tree:
            pictures.append(render_blast_tree(diagram.tree))
            seen_tree = True
    if tree is not None and tree.root.children and not seen_tree:
        pictures.append(render_blast_tree(tree))
    return [picture for picture in pictures if picture.lines]


def paint_rendered(rendered: RenderedDiagram, selected: int) -> str:
    painted: list[str] = []
    selected_row = -1
    hit: DiagramHit | None = None
    if rendered.hits and 0 <= selected < len(rendered.hits):
        hit = rendered.hits[selected]
        selected_row = hit.row
    for row, raw in enumerate(rendered.lines):
        if hit is None or row != selected_row:
            painted.append(escape(raw))
            continue
        line = raw
        if hit.col > len(line):
            line = line.ljust(hit.col)
        end = hit.col + hit.width
        if end > len(line):
            line = line.ljust(end)
        painted.append(
            f"{escape(line[: hit.col])}[reverse]{escape(line[hit.col : end])}[/reverse]{escape(line[end:])}"
        )
    return "\n".join(painted)


def wrap_index(index: int, count: int, delta: int) -> int:
    if count <= 0:
        return 0
    return (index + delta) % count


def _sequence_of(diagram: ApiDiagram) -> SequenceDiagram | None:
    if diagram.sequence is not None and diagram.sequence.steps:
        return diagram.sequence
    if diagram.mermaid and classify_mermaid(diagram.mermaid) in {"", "sequence"}:
        parsed = parse_sequence_mermaid(diagram.mermaid)
        if parsed.steps:
            return parsed
    return None


def _flow_of(diagram: ApiDiagram) -> FlowDiagram | None:
    if diagram.flow is not None and (diagram.flow.nodes or diagram.flow.edges):
        return diagram.flow
    if diagram.mermaid and classify_mermaid(diagram.mermaid) in {"", "flowchart"}:
        parsed = parse_flowchart_mermaid(diagram.mermaid)
        if parsed.nodes or parsed.edges:
            return parsed
    return None


def _schema_of(diagram: ApiDiagram) -> SchemaSnapshot | None:
    if not diagram.mermaid or classify_mermaid(diagram.mermaid) not in {"", "er"}:
        return None
    parsed = parse_er_mermaid(diagram.mermaid)
    return parsed if parsed.tables else None
