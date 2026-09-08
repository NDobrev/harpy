"""Bounded challenge of one claim. Does not erase reviewer notes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from harpy.models import Claim


@dataclass(frozen=True)
class ChallengeResult:
    claim_id: UUID
    outcome: str
    evidence: str


def challenge(claim: Claim, *, counterevidence: str) -> ChallengeResult:
    outcome = "contradicted" if counterevidence else "unresolved"
    if counterevidence and "weak" in counterevidence:
        outcome = "weakened"
    return ChallengeResult(claim_id=claim.id, outcome=outcome, evidence=counterevidence)
