"""Deterministic review routes and budget estimates."""

from __future__ import annotations

from harpy.models import LogicalChange, Risk

UNDERSTAND = "understand"
RISK = "risk"


def estimate_seconds(change: LogicalChange, extra_files: int = 0, open_items: int = 0) -> float:
    lines = max(len(change.hunks or change.hunk_ids), 1)
    duration = 45.0
    duration += min(240.0, 0.4 * lines)
    duration += min(100.0, 20.0 * extra_files)
    duration += 30.0 * open_items
    return duration


def route_changes(changes: list[LogicalChange], *, kind: str) -> list[LogicalChange]:
    if kind == RISK:
        rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        return sorted(
            changes,
            key=lambda item: (rank.get(item.risk, 4), -item.review_priority, item.id),
        )
    return sorted(changes, key=lambda item: (item.id, -item.review_priority))


def budget_prefix(
    changes: list[LogicalChange], minutes: int
) -> tuple[list[LogicalChange], list[LogicalChange]]:
    if minutes <= 0:
        raise ValueError("budget must be a positive number of minutes")
    budget = minutes * 60
    chosen: list[LogicalChange] = []
    omitted: list[LogicalChange] = []
    used = 0.0
    for change in changes:
        cost = estimate_seconds(change)
        if used + cost <= budget or not chosen:
            chosen.append(change)
            used += cost
        else:
            omitted.append(change)
    return chosen, omitted


def readiness(unreviewed: int, questions: int, blockers: int) -> str:
    if blockers:
        return f"{blockers} blocker(s) open"
    if questions:
        return f"{questions} question(s) open"
    if unreviewed:
        return f"{unreviewed} unreviewed change(s)"
    return "no outstanding review work"


def _risk_name() -> str:
    return Risk.HIGH.value
