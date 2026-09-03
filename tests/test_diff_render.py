from __future__ import annotations

from harpy.models import AnalysisResult, DiffHunk, LogicalChange, PullRequest
from harpy.tui.diff_render import line_style, render_change_diff, render_patch


def test_line_style_distinguishes_add_and_remove() -> None:
    assert line_style("+return missingDestinations") == "green"
    assert line_style("-return breakdown") == "red"
    assert line_style("@@ -1,3 +1,4 @@") == "cyan"
    assert line_style("--- a/src/fees.ts") == "bold"
    assert line_style("+++ b/src/fees.ts") == "bold"
    assert line_style("     unchanged") == ""


def test_render_patch_applies_styles() -> None:
    text = render_patch("+added\n-removed\n context\n")
    assert text.plain == "+added\n-removed\n context\n"
    styles = {str(span.style) for span in text.spans}
    assert any("green" in style for style in styles)
    assert any("red" in style for style in styles)


def test_rendered_diff_allows_wrap() -> None:
    assert render_patch("+added\n").no_wrap is False


def test_render_change_diff_includes_only_selected_hunks() -> None:
    result = AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="a",
            additions=1,
            deletions=1,
        ),
        hunks=[
            DiffHunk(
                id="H1",
                file_path="a.ts",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                patch="+keep\n",
            ),
            DiffHunk(
                id="H2",
                file_path="b.ts",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                patch="+omit\n",
            ),
        ],
    )
    change = LogicalChange(id="C1", title="one", hunk_ids=["H1"], files=["a.ts"])
    text = render_change_diff(result, change, expanded=False)
    assert "+keep" in text.plain
    assert "+omit" not in text.plain


def test_file_leaf_shows_only_this_changes_hunks_in_that_file() -> None:
    result = AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="a",
            additions=1,
            deletions=1,
        ),
        hunks=[
            DiffHunk(
                id="H1",
                file_path="a.ts",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                patch="+keep\n",
            ),
            DiffHunk(
                id="H2",
                file_path="a.ts",
                old_start=8,
                old_count=1,
                new_start=8,
                new_count=1,
                patch="+other-change\n",
            ),
            DiffHunk(
                id="H3",
                file_path="b.ts",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                patch="+other-file\n",
            ),
        ],
    )
    change = LogicalChange(id="C1", title="one", hunk_ids=["H1"], files=["a.ts"])
    text = render_change_diff(result, change, expanded=False, file_path="a.ts")
    assert "+keep" in text.plain
    assert "+other-change" not in text.plain
    assert "+other-file" not in text.plain
