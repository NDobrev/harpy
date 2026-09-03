from __future__ import annotations

from harpy.config import DEFAULT_MODEL
from harpy.review_scope import default_selection, plan_calls
from harpy.tui.scope_rows import help_line, preset_line, render_row, row_views, summary_line


def test_default_rows_and_summary() -> None:
    selection = default_selection()
    rows = row_views(selection, 0)
    rendered = [render_row(row) for row in rows]
    assert rendered[0].startswith("▸ [x] Logical changes")
    assert DEFAULT_MODEL in rendered[0]
    assert rendered[-1].startswith("  [x] Diagrams")
    assert rendered[-1].endswith("—")
    assert all("[x]" in line for line in rendered)
    assert summary_line(plan_calls(selection)) == "1 agent call · grok-4.6(7)"
    assert "p/P cycle" in preset_line("Everything")
    assert "enter run" in help_line()


def test_two_call_summary_and_unchecked_row() -> None:
    selection = default_selection()
    selection.enabled["tests"] = False
    selection.models["api"] = "gpt-5.6-sol-high"
    rows = {row.scope_id: row for row in row_views(selection, 2)}
    assert rows["tests"].checked is False
    assert "[ ]" in render_row(rows["tests"])
    assert rows["api"].model == "gpt-5.6-sol-high"
    text = summary_line(plan_calls(selection))
    assert text.startswith("2 agent calls")
    assert "grok-4.6" in text
    assert "gpt-5.6-sol" in text
