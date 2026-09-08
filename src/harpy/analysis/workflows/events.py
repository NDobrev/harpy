"""Typed analysis progress events."""

from __future__ import annotations

from uuid import UUID

from harpy.models import ProgressEvent, RunStatus


def should_apply_event(
    event: ProgressEvent,
    *,
    review_id: UUID,
    run_id: UUID,
    min_sequence: int = -1,
) -> bool:
    """Ignore events for another review, an obsolete run, or a stale sequence."""
    if event.review_id != review_id:
        return False
    if event.run_id != run_id:
        return False
    return event.sequence > min_sequence


def make_event(
    *,
    run_id: UUID,
    review_id: UUID,
    snapshot_id: UUID,
    sequence: int,
    status: RunStatus,
    message: str = "",
) -> ProgressEvent:
    return ProgressEvent(
        run_id=run_id,
        review_id=review_id,
        snapshot_id=snapshot_id,
        sequence=sequence,
        status=status,
        message=message,
    )
