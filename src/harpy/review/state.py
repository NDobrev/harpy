"""Review decisions, findings, and undo via compensating history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from harpy.models import ReviewStatus
from harpy.storage.db import ReviewStore


@dataclass(frozen=True)
class ReviewAction:
    review_id: UUID
    change_id: UUID
    status: ReviewStatus
    note: str = ""


class ReviewState:
    def __init__(self, store: ReviewStore) -> None:
        self.store = store
        self._undo: list[tuple[ReviewAction, str]] = []

    def apply(self, action: ReviewAction) -> None:
        previous = "unreviewed"
        self.store.record_decision(
            action.review_id,
            action.change_id,
            action.status.value,
            f"{action.status.value}:{action.note}:{datetime.now(UTC).isoformat()}",
        )
        self._undo.append((action, previous))

    def undo(self) -> ReviewAction | None:
        if not self._undo:
            return None
        action, previous = self._undo.pop()
        self.store.record_decision(
            action.review_id,
            action.change_id,
            previous,
            f"undo:{previous}:{datetime.now(UTC).isoformat()}",
        )
        return action
