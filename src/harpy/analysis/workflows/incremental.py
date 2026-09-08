"""Incremental analysis planning."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from harpy.models import AnalysisPlan


@dataclass(frozen=True)
class IncrementalPreview:
    reuse: int
    reanalyze: int
    new: int
    reason: str
    full: bool


def plan_incremental(
    *,
    review_id: UUID,
    invalidated_ratio: float,
    dependency_complete: bool,
    reuse: int,
    reanalyze: int,
    new: int,
    reason: str,
    force_full: bool = False,
) -> tuple[IncrementalPreview, AnalysisPlan]:
    full = force_full or not dependency_complete or invalidated_ratio > 0.6
    preview = IncrementalPreview(
        reuse=0 if full else reuse,
        reanalyze=reanalyze if not full else reuse + reanalyze + new,
        new=0 if full else new,
        reason="full analysis required" if full else reason,
        full=full,
    )
    digest = ("0" * 63) + ("1" if full else "2")
    plan = AnalysisPlan(
        id=uuid4(),
        review_id=review_id,
        snapshot_id=uuid4(),
        full=full,
        reuse_count=preview.reuse,
        reanalyze_count=preview.reanalyze,
        new_count=preview.new,
        reason=preview.reason,
        digest=digest,
    )
    return preview, plan
