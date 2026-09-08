from __future__ import annotations

from harpy.models import (
    AnalysisResult,
    Freshness,
    LogicalChange,
    PullRequest,
    ReviewStatus,
)
from harpy.tui.workspace import (
    PALETTE_ACTIONS,
    coverage_progress,
    inspector_card,
    lens_inspector,
    review_progress,
    search_changes,
    snapshot_evidence_ref,
    workspace_from_result,
)


def _change(**kwargs: object) -> LogicalChange:
    defaults: dict[str, object] = {"id": "C1", "title": "auth gate"}
    defaults.update(kwargs)
    return LogicalChange(**defaults)  # type: ignore[arg-type]


def _result(changes: list[LogicalChange] | None = None) -> AnalysisResult:
    return AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="abcdef123456",
            additions=1,
            deletions=0,
        ),
        changes=changes
        or [
            _change(id="C1", title="auth gate", files=["src/auth.py"], hunk_ids=["H1"]),
            _change(id="C2", title="docs", files=["README.md"], hunk_ids=["H2"]),
        ],
        hunks=[],
    )


def test_palette_covers_keyboard_actions() -> None:
    ids = {item.id for item in PALETTE_ACTIONS}
    required = {
        "scope",
        "expand",
        "impact",
        "questions",
        "tests",
        "omissions",
        "search",
        "palette",
        "help",
        "collapse",
        "all",
        "zoom",
        "reviewed",
        "reopen",
        "blocker",
        "note",
        "back",
        "quit",
    }
    assert required <= ids


def test_lens_change_keeps_selection() -> None:
    state = workspace_from_result(_result())
    state.select("C2", "README.md")
    state.set_lens("questions")
    assert state.selected_id == "C2"
    assert state.selected_file == "README.md"
    assert state.lens == "questions"


def test_search_ranks_exact_then_prefix_then_substring() -> None:
    changes = [
        _change(id="C1", title="token helper"),
        _change(id="C2", title="auth"),
        _change(id="C3", title="oauth"),
    ]
    ranked = search_changes(changes, "auth", notes={})
    assert [item.id for item in ranked] == ["C2", "C3"]


def test_review_and_coverage_progress_are_separate() -> None:
    result = _result()
    from harpy.models import DiffHunk

    result.hunks = [
        DiffHunk(
            id=hid, file_path=path, old_start=1, old_count=1, new_start=1, new_count=1, patch=""
        )
        for hid, path in (("H1", "src/auth.py"), ("H2", "README.md"), ("H3", "src/other.py"))
    ]
    reviewed, total = review_progress(result.changes, {"C1": ReviewStatus.REVIEWED})
    covered, hunks = coverage_progress(result)
    assert (reviewed, total) == (1, 2)
    assert (covered, hunks) == (2, 3)
    assert reviewed != covered or total != hunks


def test_evidence_ref_is_snapshot_not_live_path() -> None:
    change = _change(files=["src/auth.py"])
    ref = snapshot_evidence_ref(change, head_sha="abcdef123456")
    assert ref.startswith("snapshot abcdef123456:")
    assert not ref.startswith("/")
    assert "workspace" not in ref
    escaped = inspector_card(
        _change(title="[bold]x", before="\x1b[31mred"),
        status=ReviewStatus.UNREVIEWED,
        banner=None,
    )
    assert "\x1b" not in escaped
    assert "\\[bold]" in escaped or "[bold]" not in escaped


def test_freshness_stays_in_every_lens() -> None:
    change = _change(review_questions=["why deny?"])
    for lens in ("overview", "questions", "tests", "omissions", "behavior", "history"):
        text = lens_inspector(
            change,
            lens=lens,
            status=ReviewStatus.UNREVIEWED,
            banner="code changed",
            notes={},
            history=[],
        )
        assert "code changed" in text


def test_back_restores_source_location() -> None:
    state = workspace_from_result(_result())
    state.select("C1", "src/auth.py")
    state.set_lens("questions")
    state.select("C2", "README.md")
    anchor = state.back()
    assert anchor is not None
    assert state.selected_id == "C1"
    assert state.selected_file == "src/auth.py"
    assert state.lens == "questions"


def test_header_exposes_stale_copy() -> None:
    state = workspace_from_result(_result())
    state.freshness = Freshness.CODE_CHANGED
    header = state.header(analyzed_at="now", checked="later")
    assert "Viewing analysis" in header.analyzed
    assert "code changed" in header.badge
