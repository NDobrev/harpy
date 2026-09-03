"""Parse a mermaid subset into structured diagram IR. Fallback only."""

from __future__ import annotations

import re

from harpy.models import (
    FlowDiagram,
    FlowEdge,
    FlowNode,
    SchemaColumn,
    SchemaRelation,
    SchemaSnapshot,
    SchemaTable,
    SequenceDiagram,
    SequenceStep,
)

_ER_REL = re.compile(
    r"^\s*(\w+)\s+[|o}{\.]+(?:--|\.\.)[|o}{\.]+\s+(\w+)\s*(?::\s*(.+))?\s*$",
    re.M,
)
_ER_ENTITY = re.compile(r"(\w+)\s*\{([^}]+)\}", re.S)
_SEQ_ARROW = re.compile(
    r"^\s*(\w+)\s*(?P<arrow>-{2,3}>>?|->>|-->>)\s*(\w+)\s*:\s*(.+?)\s*$",
    re.M,
)
_PARTICIPANT = re.compile(r"^\s*participant\s+(\w+)(?:\s+as\s+.+)?\s*$", re.M | re.I)
_FLOW_HEADER = re.compile(r"^\s*(?:flowchart|graph)\s+(TD|TB|LR|RL|DT)\b", re.I | re.M)
_FLOW_NODE = re.compile(r"(\w+)(?:\[([^\]]+)\]|\{([^}]+)\}|\(\(([^)]+)\)\)|\(([^)]+)\))")
_FLOW_EDGE = re.compile(r"(\w+)\s*-->\s*(?:\|([^|]+)\|\s*)?(\w+)")


def classify_mermaid(source: str) -> str:
    lowered = source.lstrip()
    if re.search(r"\berDiagram\b", source):
        return "er"
    if re.search(r"\bsequenceDiagram\b", source):
        return "sequence"
    if (
        _FLOW_HEADER.search(source)
        or lowered.startswith("flowchart")
        or lowered.startswith("graph ")
    ):
        return "flowchart"
    return ""


def parse_er_mermaid(source: str) -> SchemaSnapshot:
    tables: dict[str, SchemaTable] = {}
    relations: list[SchemaRelation] = []
    for match in _ER_ENTITY.finditer(source):
        name = match.group(1)
        columns: list[SchemaColumn] = []
        for raw in match.group(2).splitlines():
            column = _er_column(raw)
            if column is not None:
                columns.append(column)
        tables[name] = SchemaTable(name=name, columns=columns)
    for match in _ER_REL.finditer(source):
        left, right, label = match.group(1), match.group(2), (match.group(3) or "").strip()
        tables.setdefault(left, SchemaTable(name=left))
        tables.setdefault(right, SchemaTable(name=right))
        relations.append(SchemaRelation(from_table=left, to_table=right, label=label.strip("\"'")))
    return SchemaSnapshot(tables=list(tables.values()), relations=relations)


def parse_sequence_mermaid(source: str) -> SequenceDiagram:
    actors: list[str] = []
    for match in _PARTICIPANT.finditer(source):
        name = match.group(1)
        if name not in actors:
            actors.append(name)
    steps: list[SequenceStep] = []
    for match in _SEQ_ARROW.finditer(source):
        src, dest, message = match.group(1), match.group(3), match.group(4)
        arrow = match.group("arrow")
        kind = "async" if arrow.startswith("--") else "sync"
        for name in (src, dest):
            if name not in actors:
                actors.append(name)
        steps.append(
            SequenceStep(
                from_actor=src,
                to_actor=dest,
                message=message.strip(),
                kind=kind,
            )
        )
    return SequenceDiagram(actors=actors, steps=steps)


def parse_flowchart_mermaid(source: str) -> FlowDiagram:
    nodes: dict[str, FlowNode] = {}
    edges: list[FlowEdge] = []
    for match in _FLOW_NODE.finditer(source):
        node_id = match.group(1)
        if match.group(2) is not None:
            label, shape = match.group(2), "process"
        elif match.group(3) is not None:
            label, shape = match.group(3), "decision"
        elif match.group(4) is not None:
            label, shape = match.group(4), "start"
        else:
            label, shape = match.group(5) or node_id, "process"
        nodes[node_id] = FlowNode(id=node_id, label=label.strip("\"'"), shape=shape)
    for match in _FLOW_EDGE.finditer(source):
        src, label, dest = match.group(1), (match.group(2) or "").strip(), match.group(3)
        nodes.setdefault(src, FlowNode(id=src, label=src))
        nodes.setdefault(dest, FlowNode(id=dest, label=dest))
        edges.append(FlowEdge(from_id=src, to_id=dest, label=label))
    return FlowDiagram(nodes=list(nodes.values()), edges=edges)


def _er_column(raw: str) -> SchemaColumn | None:
    line = raw.strip()
    if not line or line.startswith("%%"):
        return None
    tokens = line.split()
    if len(tokens) < 2:
        return None
    typ, name, *flags = tokens
    flag = " ".join(flags).upper()
    return SchemaColumn(
        name=name,
        type=typ,
        pk="PK" in flag or "PRIMARY" in flag,
        fk="FK" if "FK" in flag else "",
        nullable="NOT NULL" not in flag,
    )
