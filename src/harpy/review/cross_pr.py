"""Cross-PR overlap and split proposals. No Git mutation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Relationship:
    left: str
    right: str
    kind: str
    reason: str


def overlap_only(shared_filenames: bool, shared_symbols: bool, contract: bool) -> str:
    if shared_filenames and not shared_symbols and not contract:
        return "overlap"
    if shared_symbols or contract:
        return "dependency"
    return "none"
