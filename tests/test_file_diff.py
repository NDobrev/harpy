from __future__ import annotations

from harpy.models import AnalysisResult, DiffHunk, LogicalChange, PullRequest
from harpy.tui.file_diff import annotated_file_sections, other_color, stitch_file


def _pr() -> PullRequest:
    return PullRequest(
        number=1,
        title="t",
        body="",
        base_ref="main",
        head_ref="f",
        head_sha="a",
        additions=1,
        deletions=1,
    )


def test_stitch_file_shows_whole_file_and_hunk() -> None:
    after = "keep\nnew\ntail\n"
    hunk = DiffHunk(
        id="H1",
        file_path="a.ts",
        old_start=2,
        old_count=1,
        new_start=2,
        new_count=1,
        patch="@@ -2,1 +2,1 @@\n-old\n+new\n",
    )
    lines = stitch_file(after, [hunk])
    assert [(line.prefix, line.text) for line in lines] == [
        (" ", "keep"),
        ("-", "old"),
        ("+", "new"),
        (" ", "tail"),
    ]


def test_other_contexts_alternate_orange_and_blue() -> None:
    seen: list[str] = []
    assert other_color("C2", seen) == "orange1"
    assert other_color("C3", seen) == "dodger_blue2"
    assert other_color("C2", seen) == "orange1"


def test_annotated_file_labels_current_and_other_contexts() -> None:
    result = AnalysisResult(
        pr=_pr(),
        hunks=[
            DiffHunk(
                id="H1",
                file_path="a.ts",
                old_start=1,
                old_count=0,
                new_start=1,
                new_count=1,
                patch="@@ -1,0 +1,1 @@\n+keep\n",
            ),
            DiffHunk(
                id="H2",
                file_path="a.ts",
                old_start=8,
                old_count=0,
                new_start=8,
                new_count=1,
                patch="@@ -8,0 +8,1 @@\n+other-change\n",
            ),
        ],
    )
    current = LogicalChange(id="C1", title="fail closed", hunk_ids=["H1"], files=["a.ts"])
    other = LogicalChange(id="C2", title="quote reports", hunk_ids=["H2"], files=["a.ts"])
    sections = annotated_file_sections(result, current, file_path="a.ts", changes=[current, other])
    changes = [section for section in sections if section.kind == "change"]
    assert len(changes) == 2
    assert changes[0].current
    assert changes[0].gutter.startswith("current")
    assert "fail closed" in changes[0].gutter
    assert "fail closed" not in changes[0].text.plain
    assert "+keep" in changes[0].text.plain
    assert not changes[1].current
    assert changes[1].gutter.startswith("other")
    assert "quote reports" in changes[1].gutter
    assert "quote reports" not in changes[1].text.plain
    assert "+other-change" in changes[1].text.plain


def test_current_jump_targets_skip_other_contexts() -> None:
    result = AnalysisResult(
        pr=_pr(),
        hunks=[
            DiffHunk(
                id="H1",
                file_path="a.ts",
                old_start=1,
                old_count=0,
                new_start=1,
                new_count=1,
                patch="@@ -1,0 +1,1 @@\n+keep\n",
            ),
            DiffHunk(
                id="H2",
                file_path="a.ts",
                old_start=8,
                old_count=0,
                new_start=8,
                new_count=1,
                patch="@@ -8,0 +8,1 @@\n+other-change\n",
            ),
            DiffHunk(
                id="H3",
                file_path="a.ts",
                old_start=12,
                old_count=0,
                new_start=12,
                new_count=1,
                patch="@@ -12,0 +12,1 @@\n+keep-two\n",
            ),
        ],
    )
    current = LogicalChange(id="C1", title="fail closed", hunk_ids=["H1", "H3"], files=["a.ts"])
    other = LogicalChange(id="C2", title="quote reports", hunk_ids=["H2"], files=["a.ts"])
    sections = annotated_file_sections(result, current, file_path="a.ts", changes=[current, other])
    jumps = [section for section in sections if section.kind == "change" and section.current]
    assert [section.title for section in jumps] == ["fail closed", "fail closed"]
    assert "+keep-two" in jumps[1].text.plain
