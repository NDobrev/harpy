"""Intent sources stay separate; conflicts become questions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentSource:
    kind: str
    text: str


def conflict_question(task: IntentSource, description: IntentSource) -> str | None:
    if (
        task.text.strip()
        and description.text.strip()
        and task.text.strip() != description.text.strip()
    ):
        return "Intent sources disagree; which requirement is authoritative?"
    return None
