"""Pure scoring over typed models. Imports harpy.models only."""

from __future__ import annotations

from harpy.models import LogicalChange, Risk, ScoringWeights, SemanticChangeDraft, StaticSignals

AUTH_DOMAINS = {"authorization", "authentication", "auth", "AUTH"}
CRITICAL_DOMAINS = {
    "authentication",
    "authorization",
    "billing",
    "payments",
    "tenant isolation",
    "data deletion",
    "encryption",
    "secrets",
}


def semantic_score(change: SemanticChangeDraft, weights: ScoringWeights) -> float:
    return (
        change.behavior_change * weights.behavior_weight
        + change.business_impact * weights.business_weight
        + change.blast_radius * weights.blast_weight
        + change.security_sensitivity * weights.security_weight
        + change.data_sensitivity * weights.data_weight
        + change.novelty * weights.novelty_weight
    )


def static_score(signals: list[StaticSignals]) -> float:
    if not signals:
        return 0.0
    return max(item.raw_score for item in signals)


def noise_penalty(signals: list[StaticSignals]) -> float:
    penalty = 0.0
    for item in signals:
        if item.generated:
            penalty = min(penalty, -abs(item.raw_score) if item.raw_score < 0 else -30)
        if item.lockfile:
            penalty = min(penalty, -40)
        if item.snapshot:
            penalty = min(penalty, -20)
    return abs(penalty)


def normalize(value: float, *, lo: float = -40.0, hi: float = 120.0) -> float:
    clamped = max(lo, min(hi, value))
    return (clamped - lo) / (hi - lo) * 100.0


def floor_risk(risk: Risk, domains: list[str], categories: list[str]) -> Risk:
    labels = {item.lower() for item in domains} | {item.lower() for item in categories}
    order = [Risk.LOW, Risk.MEDIUM, Risk.HIGH, Risk.CRITICAL]
    current = risk
    if labels & {item.lower() for item in AUTH_DOMAINS} or "auth" in labels:
        current = order[max(order.index(current), order.index(Risk.HIGH))]
    if labels & {item.lower() for item in CRITICAL_DOMAINS}:
        current = order[max(order.index(current), order.index(Risk.HIGH))]
    return current


def parse_risk(raw: str) -> Risk:
    try:
        return Risk(raw.upper())
    except ValueError:
        mapping = {
            "low": Risk.LOW,
            "medium": Risk.MEDIUM,
            "high": Risk.HIGH,
            "critical": Risk.CRITICAL,
        }
        return mapping.get(raw.lower(), Risk.LOW)


def review_priority(importance: float, unexpectedness: float, weights: ScoringWeights) -> float:
    priority = importance * weights.importance_mix + unexpectedness * weights.unexpectedness_mix
    if importance > weights.critical_threshold and unexpectedness > weights.critical_threshold:
        priority += weights.critical_boost
    return priority


def score_change(
    draft: SemanticChangeDraft,
    signals: list[StaticSignals],
    weights: ScoringWeights,
) -> LogicalChange:
    static = static_score(signals)
    penalty = noise_penalty(signals)
    importance = normalize(semantic_score(draft, weights) * 8.0 + static - penalty)
    unexpected = draft.unexpectedness * 100.0 if draft.unexpectedness <= 1 else draft.unexpectedness
    categories = [cat for item in signals for cat in item.categories]
    risk = floor_risk(parse_risk(draft.risk), draft.domains, categories)
    hunks = draft.hunk_ids or []
    return LogicalChange(
        id=draft.id,
        title=draft.title,
        importance=importance,
        confidence=draft.confidence if draft.confidence <= 1 else draft.confidence / 100.0,
        unexpectedness=unexpected,
        risk=risk.value,
        review_priority=review_priority(importance, unexpected, weights),
        business_impact=draft.business_impact,
        behavior_change=draft.behavior_change,
        blast_radius=draft.blast_radius,
        security_sensitivity=draft.security_sensitivity,
        data_sensitivity=draft.data_sensitivity,
        novelty=draft.novelty,
        before=draft.before,
        after=draft.after,
        why=draft.why,
        business_effect=draft.business_effect,
        files=list(draft.files),
        hunks=list(hunks),
        hunk_ids=list(hunks),
        affected_symbols=list(draft.affected_symbols),
        affected_components=list(draft.affected_components),
        review_questions=list(draft.review_questions),
        possible_omissions=list(draft.possible_omissions),
        tests=list(draft.tests),
        domains=list(draft.domains),
    )
