"""Evidence-first change cards and freshness copy."""

from __future__ import annotations

from dataclasses import dataclass

from harpy.models import Freshness, ReportLogicalChange


@dataclass(frozen=True)
class ChangeCard:
    behavior: str
    consequence: str
    evidence: str
    action: str
    numeric_hidden: bool = True


@dataclass(frozen=True)
class FreshnessHeader:
    analyzed: str
    latest: str
    badge: str


def card_for(change: ReportLogicalChange, *, action: str) -> ChangeCard:
    return ChangeCard(
        behavior=change.title,
        consequence="",
        evidence=", ".join(change.hunk_ids) or "none found within assessed context",
        action=action,
    )


def freshness_header(
    *, analyzed_rev: str, analyzed_at: str, latest_rev: str, checked: str, freshness: Freshness
) -> FreshnessHeader:
    badge = {
        Freshness.CURRENT: "current",
        Freshness.CODE_CHANGED: "code changed",
        Freshness.INTENT_CHANGED: "intent changed",
        Freshness.CODE_AND_INTENT_CHANGED: "code and intent changed",
        Freshness.LOCAL_CHANGED: "working tree changed",
        Freshness.CHECKING: "checking for updates",
        Freshness.UNKNOWN: "freshness unknown",
    }[freshness]
    return FreshnessHeader(
        analyzed=f"Viewing analysis: {analyzed_rev} · {analyzed_at}",
        latest=f"Latest observed: {latest_rev} · checked {checked}",
        badge=badge,
    )


def escape_plain(text: str) -> str:
    return text.replace("\x1b", "").replace("[", "\\[")
