from __future__ import annotations

from harpy.models import (
    AnalysisResult,
    ApiEndpointImpact,
    LogicalChange,
    PullRequest,
)
from harpy.tui.impact_entries import (
    ImpactEntry,
    change_for_impact,
    entries_from_result,
    rows_from_entries,
)


def _pr() -> PullRequest:
    return PullRequest(
        number=1,
        title="t",
        body="",
        base_ref="main",
        head_ref="f",
        head_sha="a",
        additions=1,
        deletions=0,
    )


def test_label_markup_colors_tags_only() -> None:
    item = ImpactEntry(
        kind="api",
        api=ApiEndpointImpact(
            method="POST",
            path="/v1/settle",
            summary="ops settle",
            business_logic=True,
            security=True,
            breaking=True,
        ),
    )
    rows = rows_from_entries([item])
    label = rows[0].label
    assert "[bold cyan]API[/]" in label
    assert "[bold yellow]BL[/]" in label
    assert "[bold #d946ef]SEC[/]" in label
    assert "[bold red]⚠[/]" in label
    assert "POST /v1/settle" in label
    assert "[bold cyan]POST" not in label


def test_change_for_impact_uses_change_id_then_file() -> None:
    result = AnalysisResult(
        pr=_pr(),
        changes=[
            LogicalChange(id="C1", title="settle", files=["src/routes/v1.ts"], hunk_ids=["H1"]),
            LogicalChange(id="C2", title="other", files=["src/other.ts"], hunk_ids=["H2"]),
        ],
        api_impacts=[
            ApiEndpointImpact(
                change_id="C1", method="POST", path="/v1/settle", files=["src/routes/v1.ts"]
            )
        ],
    )
    item = entries_from_result(result)[0]
    linked = change_for_impact(result, item, "src/routes/v1.ts")
    assert linked is not None
    assert linked.id == "C1"
    orphan = ImpactEntry(
        kind="api",
        api=ApiEndpointImpact(method="GET", path="/v1/x", files=["missing.ts"]),
    )
    fallback = change_for_impact(result, orphan, "missing.ts")
    assert fallback is not None
    assert fallback.files == ["missing.ts"]
