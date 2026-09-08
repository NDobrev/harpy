from __future__ import annotations

from harpy.tui.layout import workspace_layout


def test_pilot_widths() -> None:
    wide = workspace_layout(160, 48)
    assert not wide.single_pane
    assert not wide.inspector_drawer
    mid = workspace_layout(110, 32)
    assert mid.inspector_drawer
    narrow = workspace_layout(80, 24)
    assert narrow.single_pane
    assert narrow.compact_notice
