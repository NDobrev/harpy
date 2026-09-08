"""Agent-output quality finding categories."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

CATEGORIES = (
    "unnecessary_complexity",
    "existing_implementation",
    "suspicious_test_weakening",
    "incomplete_wiring",
)


@dataclass(frozen=True)
class QualityFinding:
    id: UUID
    category: str
    why: str
    countercheck: str
    action: str


def limit_findings(items: list[QualityFinding], *, limit: int = 5) -> list[QualityFinding]:
    return items[:limit]


def new_finding(category: str, why: str) -> QualityFinding:
    return QualityFinding(
        id=uuid4(),
        category=category,
        why=why,
        countercheck="could be legitimate restructuring",
        action="confirm or dismiss",
    )
