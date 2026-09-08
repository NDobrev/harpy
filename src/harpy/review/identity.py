"""Logical-change identity matching and lineage."""

from __future__ import annotations

from dataclasses import dataclass

from harpy.models import LogicalChangeIdentity


@dataclass(frozen=True)
class Match:
    predecessor: LogicalChangeIdentity
    successor: LogicalChangeIdentity
    score: float
    kind: str


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def candidate_score(*, content: float | None, symbols: float | None) -> float:
    weights: list[tuple[float, float]] = []
    if content is not None:
        weights.append((0.7, content))
    if symbols is not None:
        weights.append((0.3, symbols))
    if not weights:
        return 0.0
    total = sum(weight for weight, _ in weights)
    return sum(weight * value for weight, value in weights) / total


def match_identities(
    previous: list[LogicalChangeIdentity],
    current: list[LogicalChangeIdentity],
    *,
    content_sets: dict[str, set[str]],
    symbol_sets: dict[str, set[str]],
) -> list[Match]:
    matches: list[Match] = []
    used: set[str] = set()
    for new in current:
        exact = next(
            (old for old in previous if set(old.fingerprints) & set(new.fingerprints)), None
        )
        if exact is not None:
            matches.append(Match(exact, new, 1.0, "fingerprint"))
            used.add(str(exact.id))
            continue
        scored: list[tuple[float, LogicalChangeIdentity]] = []
        for old in previous:
            if str(old.id) in used:
                continue
            content = jaccard(
                content_sets.get(str(old.id), set()), content_sets.get(str(new.id), set())
            )
            symbols = jaccard(
                symbol_sets.get(str(old.id), set()), symbol_sets.get(str(new.id), set())
            )
            score = candidate_score(content=content, symbols=symbols)
            scored.append((score, old))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            continue
        best, winner = scored[0][0], scored[0][1]
        second = scored[1][0] if len(scored) > 1 else 0.0
        if best >= 0.85 and (best - second) >= 0.20:
            matches.append(Match(winner, new, best, "scored"))
            used.add(str(winner.id))
    return matches
