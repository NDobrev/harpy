"""ASCII schema visualizer. Terminal boxes, not mermaid source."""

from __future__ import annotations

from harpy.analysis.diagrams.compat import render_sequence, visualize_diagrams
from harpy.analysis.diagrams.mermaid import parse_er_mermaid
from harpy.analysis.diagrams.schema import (
    has_structural_change,
    merge_snapshots,
    render_before_after,
    render_schema,
    schema_from_patch,
    split_before_after,
)

__all__ = [
    "has_structural_change",
    "merge_snapshots",
    "parse_er_mermaid",
    "render_before_after",
    "render_schema",
    "render_sequence",
    "schema_from_patch",
    "split_before_after",
    "visualize_diagrams",
]
