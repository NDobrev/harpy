from __future__ import annotations

from harpy.models import LogicalChange
from harpy.tui.widgets.change_list import change_label


def test_selected_row_has_cursor_prefix() -> None:
    change = LogicalChange(id="C1", title="fail closed", risk="HIGH", review_priority=80)
    assert change_label(change, selected=True).startswith("▸ ")
    assert change_label(change, selected=False).startswith("  ")
    assert "fail closed" in change_label(change, selected=True)
