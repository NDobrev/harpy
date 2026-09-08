from __future__ import annotations

from uuid import uuid4

from harpy.analysis.behavior import scenario
from harpy.models import (
    Claim,
    ClaimAssessment,
    ClaimKind,
    Freshness,
    LogicalChangeIdentity,
    ReportLogicalChange,
)
from harpy.review.challenge import challenge
from harpy.review.cross_pr import overlap_only
from harpy.review.quality import CATEGORIES, limit_findings, new_finding
from harpy.review.views import cell
from harpy.tui.cards import card_for, escape_plain, freshness_header


def test_freshness_visible_and_not_color_only() -> None:
    header = freshness_header(
        analyzed_rev="abc",
        analyzed_at="now",
        latest_rev="def",
        checked="later",
        freshness=Freshness.CODE_CHANGED,
    )
    assert "Viewing analysis" in header.analyzed
    assert "code changed" in header.badge


def test_change_card_hides_numeric_by_default() -> None:
    change = ReportLogicalChange(
        identity=LogicalChangeIdentity(id=uuid4(), revision_local_ids=["C1"]),
        title="auth",
        hunk_ids=["H1"],
    )
    card = card_for(change, action="mark reviewed")
    assert card.numeric_hidden
    assert card.behavior == "auth"


def test_escape_control_characters() -> None:
    assert "\x1b" not in escape_plain("\x1b[31mred")


def test_scenario_unknown_sides() -> None:
    item = scenario(actor="user", input_text="delete")
    assert item.before == "unknown"
    assert item.after == "unknown"


def test_quality_findings_capped() -> None:
    items = [new_finding(CATEGORIES[0], "why") for _ in range(8)]
    assert len(limit_findings(items)) == 5


def test_challenge_keeps_original_claim() -> None:
    claim = Claim(
        id=uuid4(),
        change_id=uuid4(),
        kind=ClaimKind.INFERENCE,
        statement="safe",
        assessment=ClaimAssessment.SUPPORTED,
    )
    result = challenge(claim, counterevidence="weak counter")
    assert result.claim_id == claim.id
    assert claim.statement == "safe"


def test_missing_permission_is_unknown_not_deny() -> None:
    unknown = cell("admin", "delete", None)
    assert unknown.unknown
    assert unknown.value != "deny"


def test_shared_filename_is_overlap_not_dependency() -> None:
    assert overlap_only(True, False, False) == "overlap"
