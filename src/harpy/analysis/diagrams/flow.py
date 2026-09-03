"""Compact vertical flowchart boxes."""

from __future__ import annotations

from collections import defaultdict

from harpy.models import DiagramHit, FlowDiagram, FlowEdge, FlowNode, RenderedDiagram

_CHANGE = {"add": "+", "drop": "-", "alter": "~"}
_INNER = 18


def render_flow_diagram(diagram: FlowDiagram) -> RenderedDiagram:
    by_id = {node.id or node.label: node for node in diagram.nodes if node.id or node.label}
    for edge in diagram.edges:
        by_id.setdefault(edge.from_id, FlowNode(id=edge.from_id, label=edge.from_id))
        by_id.setdefault(edge.to_id, FlowNode(id=edge.to_id, label=edge.to_id))
    if not by_id:
        return RenderedDiagram(kind="flowchart", title="FLOW")
    order = _order(by_id, diagram.edges)
    outgoing: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in diagram.edges:
        outgoing[edge.from_id].append((edge.to_id, edge.label))
    lines = ["FLOW", ""]
    hits: list[DiagramHit] = []
    seen: set[str] = set()
    for index, node_id in enumerate(order):
        if node_id in seen:
            continue
        seen.add(node_id)
        node = by_id[node_id]
        box = _render_node(node)
        if index:
            labels = [
                label
                for src, dests in outgoing.items()
                if src in seen
                for dest, label in dests
                if dest == node_id
            ]
            lines.extend(_arrow(labels[0] if labels else ""))
        start = len(lines)
        lines.extend(box)
        label = _node_label(node)
        for row, line in enumerate(lines[start:], start=start):
            col = line.find(label)
            if col >= 0:
                hits.append(
                    DiagramHit(
                        row=row,
                        col=col,
                        width=len(label),
                        node_id=f"flow:{node.id or label}",
                        path=node.path,
                    )
                )
                break
    return RenderedDiagram(title="FLOW", kind="flowchart", lines=lines, hits=hits)


def _order(nodes: dict[str, FlowNode], edges: list[FlowEdge]) -> list[str]:
    incoming: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.from_id in nodes and edge.to_id in nodes:
            children[edge.from_id].append(edge.to_id)
            incoming[edge.to_id] += 1
    ready = [node_id for node_id in nodes if incoming[node_id] == 0]
    ordered: list[str] = []
    seen: set[str] = set()
    while ready:
        node_id = ready.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        ordered.append(node_id)
        for dest in children[node_id]:
            incoming[dest] -= 1
            if incoming[dest] == 0:
                ready.append(dest)
    for node_id in nodes:
        if node_id not in seen:
            ordered.append(node_id)
    return ordered


def _node_label(node: FlowNode) -> str:
    mark = _CHANGE.get(node.change, "")
    label = node.label or node.id
    return f"{label} {mark}".strip() if mark else label


def _render_node(node: FlowNode) -> list[str]:
    label = _node_label(node)
    if node.shape == "decision":
        body = f"{{ {label} }}"
        return [body]
    inner = max(_INNER, len(label) + 2)
    edge = "─" * inner
    return [f"┌{edge}┐", f"│{label.center(inner)}│", f"└{edge}┘"]


def _arrow(label: str) -> list[str]:
    pad = " " * 10
    lines = [f"{pad}│"]
    if label:
        lines.append(f"{pad}│ {label}")
    lines.append(f"{pad}▼")
    return lines
