"""Citation validation and coverage accounting."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

from harpy.git.source import SourceRead
from harpy.models import (
    Claim,
    ClaimAssessment,
    CoverageEntry,
    LineRange,
    ReportLogicalChange,
    SourceEvidence,
)


class InvalidEvidenceError(ValueError):
    pass


def excerpt_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def validate_citation(evidence: SourceEvidence, source: SourceRead) -> SourceEvidence:
    if not source.available:
        raise InvalidEvidenceError(source.reason or "source unavailable")
    if source.path != evidence.path:
        raise InvalidEvidenceError("path does not match source")
    if evidence.excerpt not in source.text:
        raise InvalidEvidenceError("excerpt does not match source")
    if excerpt_hash(evidence.excerpt) != evidence.excerpt_hash:
        raise InvalidEvidenceError("excerpt hash mismatch")
    lines = source.text.splitlines()
    if evidence.end_line > len(lines) or evidence.start_line < 1:
        raise InvalidEvidenceError("line range is outside source")
    return evidence


def reconcile_coverage(
    hunk_ids: Sequence[str],
    changes: Sequence[ReportLogicalChange],
) -> list[CoverageEntry]:
    owned: dict[str, list[str]] = {hunk_id: [] for hunk_id in hunk_ids}
    for change in changes:
        local = change.identity.revision_local_ids[0] if change.identity.revision_local_ids else ""
        for hunk_id in change.hunk_ids:
            owned.setdefault(hunk_id, []).append(local or str(change.identity.id))
    entries: list[CoverageEntry] = []
    for hunk_id in hunk_ids:
        owners = owned.get(hunk_id, [])
        if not owners:
            entries.append(
                CoverageEntry(
                    hunk_id=hunk_id,
                    primary_owner="unclassified",
                    exclusion_reason="omitted from grouping",
                )
            )
            continue
        entries.append(
            CoverageEntry(
                hunk_id=hunk_id,
                primary_owner=owners[0],
                secondary_owners=owners[1:],
                supplied_ranges=[LineRange(start_line=1, end_line=1)],
            )
        )
    return entries


def unique_hunk_count(entries: Sequence[CoverageEntry]) -> int:
    return len({entry.hunk_id for entry in entries})


def claim_is_not_proven(claim: Claim) -> bool:
    return claim.assessment != ClaimAssessment.SUPPORTED or bool(claim.limitations)
