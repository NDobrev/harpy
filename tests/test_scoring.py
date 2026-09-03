from __future__ import annotations

from harpy.analysis.scoring import review_priority, score_change
from harpy.models import ScoringWeights, SemanticChangeDraft, StaticSignals


def test_auth_risk_floor() -> None:
    draft = SemanticChangeDraft(
        id="C1",
        title="org admin delete",
        business_impact=9,
        behavior_change=10,
        blast_radius=8,
        security_sensitivity=9,
        risk="low",
        domains=["authorization"],
        hunk_ids=["H1"],
        confidence=0.9,
        unexpectedness=0.2,
    )
    signals = [
        StaticSignals(file_path="src/auth/permissions.py", raw_score=30, categories=["AUTH"])
    ]
    change = score_change(draft, signals, ScoringWeights())
    assert change.risk in {"HIGH", "CRITICAL"}
    assert change.importance > 50


def test_unexpectedness_boost() -> None:
    weights = ScoringWeights()
    boosted = review_priority(80, 80, weights)
    plain = review_priority(80, 10, weights)
    assert boosted > plain
    assert boosted - (80 * 0.7 + 80 * 0.3) == weights.critical_boost
