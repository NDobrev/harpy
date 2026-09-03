"""Stable schema_view helpers. Existing tests import these signatures."""

from __future__ import annotations

import re

from harpy.analysis.diagrams.mermaid import parse_er_mermaid
from harpy.analysis.diagrams.schema import has_structural_change, render_before_after, render_schema
from harpy.models import SchemaSnapshot

_SEQ_ARROW = re.compile(
    r"^\s*(\w+)\s*(?:-{2,3}>>?|->>|-->>)\s*(\w+)\s*:\s*(.+?)\s*$",
    re.M,
)


def render_sequence(source: str) -> str:
    steps = _SEQ_ARROW.findall(source)
    if not steps:
        return ""
    lines = ["SEQUENCE", ""]
    for src, dest, message in steps:
        lines.append(f"{src}  ── {message.strip()} ──►  {dest}")
    return "\n".join(lines)


def visualize_diagrams(
    *,
    schema: SchemaSnapshot,
    mermaid: list[str],
    highlight: str = "",
    width: int = 40,
) -> str:
    parts: list[str] = []
    if schema.tables:
        if has_structural_change(schema):
            parts.append(render_before_after(schema, highlight=highlight, width=width))
        else:
            parts.append(render_schema(schema, highlight=highlight, width=width))
        return "\n".join(parts)
    for source in mermaid:
        parsed = parse_er_mermaid(source)
        if parsed.tables:
            parts.append(render_schema(parsed, highlight=highlight, width=width))
            continue
        sequence = render_sequence(source)
        if sequence:
            parts.append(sequence)
    return "\n\n".join(part for part in parts if part)
