"""Responsive workspace regions. Width drives pane arrangement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceLayout:
    width: int
    height: int
    navigator: float
    canvas: float
    inspector: float
    inspector_drawer: bool
    single_pane: bool
    compact_notice: bool


def workspace_layout(width: int, height: int) -> WorkspaceLayout:
    compact = width <= 80 or height <= 24
    if width >= 140:
        return WorkspaceLayout(width, height, 0.28, 0.47, 0.25, False, False, compact)
    if width >= 100:
        return WorkspaceLayout(width, height, 0.30, 0.70, 0.0, True, False, compact)
    return WorkspaceLayout(width, height, 1.0, 1.0, 1.0, False, True, compact)
