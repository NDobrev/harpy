"""Behavior scenarios with explicit unknown sides."""

from __future__ import annotations

from uuid import uuid4

from harpy.models import Scenario


def scenario(
    *,
    actor: str,
    input_text: str,
    before: str = "",
    after: str = "",
    inferred: bool = True,
) -> Scenario:
    if not before and not after:
        before = "unknown"
        after = "unknown"
    return Scenario(
        id=uuid4(),
        actor=actor,
        input=input_text,
        before=before or "unknown",
        after=after or "unknown",
        inferred=inferred,
    )


def same_schema(left: Scenario, right: Scenario) -> bool:
    return (left.actor, left.input, left.before, left.after) == (
        right.actor,
        right.input,
        right.before,
        right.after,
    )
