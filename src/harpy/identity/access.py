"""Role and repository-grant capability matrix."""

from __future__ import annotations

from typing import Literal

Action = Literal[
    "read",
    "mutate",
    "acquire",
    "analyze",
    "cancel_own",
    "cancel_other",
    "manage_tenant",
    "preferences",
]

WRITE_ROLES = frozenset({"administrator", "reviewer"})
READ_GRANTS = frozenset({"read", "review"})


def allows(*, role: str, grant: str | None, action: Action) -> bool:
    if action == "manage_tenant":
        return role == "administrator"
    if action == "preferences":
        return role in {"administrator", "reviewer", "viewer"}
    if grant not in READ_GRANTS:
        return False
    if action == "read":
        return True
    can_write = role in WRITE_ROLES and grant == "review"
    if action in {"mutate", "acquire", "analyze", "cancel_own"}:
        return can_write
    if action == "cancel_other":
        return role == "administrator" and grant == "review"
    return False
