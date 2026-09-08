"""Permissions, deployment, and architecture view records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatrixCell:
    principal: str
    action: str
    value: str
    evidence: str = ""
    unknown: bool = False


def cell(principal: str, action: str, value: str | None, evidence: str = "") -> MatrixCell:
    if value is None:
        return MatrixCell(principal, action, "unknown", evidence="", unknown=True)
    return MatrixCell(principal, action, value, evidence=evidence, unknown=False)
