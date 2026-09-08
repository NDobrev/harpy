"""Draft GitHub reviews and idempotent submission markers."""

from __future__ import annotations

from uuid import UUID, uuid4


def submission_marker(submission_id: UUID) -> str:
    return f"<!-- harpy-submission:{submission_id} -->"


def new_submission() -> UUID:
    return uuid4()
