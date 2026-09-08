from __future__ import annotations

from uuid import uuid4

import pytest

from harpy.evidence.validate import (
    InvalidEvidenceError,
    reconcile_coverage,
    unique_hunk_count,
    validate_citation,
)
from harpy.git.source import SourceRead
from harpy.models import (
    Claim,
    ClaimAssessment,
    ClaimKind,
    LogicalChangeIdentity,
    ReportLogicalChange,
    SourceEvidence,
)


def _sha(n: int) -> str:
    return f"{n:064x}"


def test_invented_path_is_invalid() -> None:
    source = SourceRead(path="src/a.py", side="head", available=True, text="return 1\n")
    evidence = SourceEvidence(
        id=uuid4(),
        content_key=_sha(1),
        repository_id=uuid4(),
        snapshot_id=uuid4(),
        side="head",
        path="src/missing.py",
        blob_hash=_sha(2),
        start_line=1,
        end_line=1,
        excerpt="nope",
        excerpt_hash=_sha(3),
        source_kind="diff",
    )
    with pytest.raises(InvalidEvidenceError):
        validate_citation(evidence, source)


def test_omitted_hunks_become_unclassified() -> None:
    identity = LogicalChangeIdentity(id=uuid4(), revision_local_ids=["C1"])
    change = ReportLogicalChange(identity=identity, title="auth", hunk_ids=["H1"])
    coverage = reconcile_coverage(["H1", "H2", "H3", "H4"], [change])
    assert unique_hunk_count(coverage) == 4
    unclassified = [item for item in coverage if item.primary_owner == "unclassified"]
    assert len(unclassified) == 3


def test_shared_hunk_counted_once() -> None:
    a = LogicalChangeIdentity(id=uuid4(), revision_local_ids=["C1"])
    b = LogicalChangeIdentity(id=uuid4(), revision_local_ids=["C2"])
    coverage = reconcile_coverage(
        ["H1"],
        [
            ReportLogicalChange(identity=a, title="one", hunk_ids=["H1"]),
            ReportLogicalChange(identity=b, title="two", hunk_ids=["H1"]),
        ],
    )
    assert unique_hunk_count(coverage) == 1
    assert coverage[0].secondary_owners == ["C2"]


def test_supported_claim_is_not_automatically_proven() -> None:
    claim = Claim(
        id=uuid4(),
        change_id=uuid4(),
        kind=ClaimKind.OBSERVATION,
        statement="admins can delete",
        assessment=ClaimAssessment.SUPPORTED,
        limitations=["citation confirms location, not truth"],
    )
    assert claim.limitations
