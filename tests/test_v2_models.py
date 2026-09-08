from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from harpy.models import (
    REPORT_SCHEMA_VERSION,
    AnalysisReport,
    AnalysisResponse,
    AnalysisResult,
    Claim,
    ClaimAssessment,
    ClaimKind,
    ContextRequest,
    CoverageEntry,
    DependencyManifest,
    ImpactRecord,
    LineRange,
    LogicalChange,
    LogicalChangeIdentity,
    PullRequest,
    ReportAssemblyError,
    ReportLogicalChange,
    ReportProvenance,
    RetrievalRequest,
    RevisionSnapshot,
    RunStatus,
    ScopeAssessment,
    ScopeStatus,
    SemanticAnalysisResult,
    SourceEvidence,
    assemble_analysis_report,
)


def _sha(n: int = 1) -> str:
    return f"{n:064x}"


def _utc() -> datetime:
    return datetime(2026, 9, 8, 14, 30, tzinfo=UTC)


def _identity() -> LogicalChangeIdentity:
    return LogicalChangeIdentity(id=uuid4(), revision_local_ids=["C1"], fingerprints=[_sha(2)])


def _evidence(*, snapshot_id: UUID, change_path: str = "src/auth.py") -> SourceEvidence:
    return SourceEvidence(
        id=uuid4(),
        content_key=_sha(3),
        repository_id=uuid4(),
        snapshot_id=snapshot_id,
        side="head",
        path=change_path,
        blob_hash=_sha(4),
        start_line=10,
        end_line=12,
        excerpt="return allow",
        excerpt_hash=_sha(5),
        source_kind="diff",
    )


def _report(**overrides: object) -> AnalysisReport:
    snapshot_id = uuid4()
    identity = _identity()
    evidence = _evidence(snapshot_id=snapshot_id)
    payload: dict[str, object] = {
        "id": uuid4(),
        "snapshot_id": snapshot_id,
        "scope_results": [
            ScopeAssessment(scope_id="changes", status=ScopeStatus.COMPLETE, prompt_version="12")
        ],
        "logical_changes": [ReportLogicalChange(identity=identity, title="auth", hunk_ids=["H1"])],
        "claims": [
            Claim(
                id=uuid4(),
                change_id=identity.id,
                kind=ClaimKind.OBSERVATION,
                statement="Admins can delete users.",
                evidence_ids=[evidence.id],
                assessment=ClaimAssessment.SUPPORTED,
                limitations=["citation confirms location, not truth"],
            )
        ],
        "impacts": [
            ImpactRecord(kind="permission", summary="delete user", change_ids=[identity.id])
        ],
        "coverage": [CoverageEntry(hunk_id="H1", primary_owner="C1")],
        "evidence": [evidence],
        "dependency_manifest": DependencyManifest(source_files={"src/auth.py": _sha(6)}),
        "provenance": ReportProvenance(run_id=uuid4(), reused_artifacts=["scope:changes"]),
    }
    payload.update(overrides)
    return AnalysisReport.model_validate(payload)


def test_report_schema_version_is_two() -> None:
    report = _report()
    assert report.schema_version == REPORT_SCHEMA_VERSION == 2
    assert report.provenance.schema_version == 2


def test_v2_report_round_trip_keeps_revision_and_provenance() -> None:
    report = _report()
    restored = AnalysisReport.model_validate_json(report.model_dump_json())
    assert restored.snapshot_id == report.snapshot_id
    assert restored.provenance.run_id == report.provenance.run_id
    assert restored.provenance.reused_artifacts == ["scope:changes"]
    assert restored.evidence[0].blob_hash == report.evidence[0].blob_hash
    assert restored.logical_changes[0].identity.id == report.logical_changes[0].identity.id
    assert restored.claims[0].limitations == report.claims[0].limitations


def test_snapshot_round_trip_keeps_shas() -> None:
    snapshot = RevisionSnapshot(
        id=uuid4(),
        target_id=uuid4(),
        base_tip_sha="a" * 40,
        comparison_base_sha="b" * 40,
        head_sha="c" * 40,
        title="Allow org admins",
        body="task: preserve audit",
        diff_digest=_sha(7),
        created_at=_utc(),
        acquisition_complete=True,
    )
    restored = RevisionSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored.base_tip_sha == snapshot.base_tip_sha
    assert restored.comparison_base_sha == snapshot.comparison_base_sha
    assert restored.head_sha == snapshot.head_sha
    assert restored.diff_digest == snapshot.diff_digest


def test_invalid_enum_is_rejected() -> None:
    with pytest.raises(ValueError):
        ClaimAssessment("cached")
    with pytest.raises(ValueError):
        RunStatus("done")
    with pytest.raises(ValidationError):
        ScopeAssessment.model_validate({"scope_id": "changes", "status": "cached"})


def test_invalid_evidence_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LineRange(start_line=10, end_line=4)
    with pytest.raises(ValidationError):
        LineRange(start_line=0, end_line=2)
    snapshot_id = uuid4()
    with pytest.raises(ValidationError):
        SourceEvidence(
            id=uuid4(),
            content_key=_sha(3),
            repository_id=uuid4(),
            snapshot_id=snapshot_id,
            side="head",
            path="src/auth.py",
            blob_hash=_sha(4),
            start_line=8,
            end_line=3,
            excerpt="x",
            excerpt_hash=_sha(5),
            source_kind="diff",
        )


def test_path_traversal_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SourceEvidence(
            id=uuid4(),
            content_key=_sha(3),
            repository_id=uuid4(),
            snapshot_id=uuid4(),
            side="base",
            path="../secrets/key",
            blob_hash=_sha(4),
            start_line=1,
            end_line=1,
            excerpt="x",
            excerpt_hash=_sha(5),
            source_kind="file",
        )


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RevisionSnapshot(
            id=uuid4(),
            target_id=uuid4(),
            base_tip_sha="a",
            comparison_base_sha="b",
            head_sha="c",
            diff_digest=_sha(7),
            created_at=datetime(2026, 9, 8, 14, 30),
        )


def test_aware_non_utc_timestamp_is_normalized() -> None:
    eastern = datetime(2026, 9, 8, 12, 30, tzinfo=timezone(timedelta(hours=-4)))
    snapshot = RevisionSnapshot(
        id=uuid4(),
        target_id=uuid4(),
        base_tip_sha="a",
        comparison_base_sha="b",
        head_sha="c",
        diff_digest=_sha(7),
        created_at=eastern,
    )
    assert snapshot.created_at.utcoffset() == timedelta(0)
    assert snapshot.created_at.hour == 16


def test_cross_record_unknown_change_is_rejected() -> None:
    with pytest.raises((ValidationError, ReportAssemblyError)):
        _report(
            claims=[
                Claim(
                    id=uuid4(),
                    change_id=uuid4(),
                    kind=ClaimKind.INFERENCE,
                    statement="missing change",
                    assessment=ClaimAssessment.LIMITED,
                )
            ]
        )


def test_cross_record_unknown_evidence_is_rejected() -> None:
    snapshot_id = uuid4()
    identity = _identity()
    with pytest.raises((ValidationError, ReportAssemblyError)):
        AnalysisReport(
            id=uuid4(),
            snapshot_id=snapshot_id,
            logical_changes=[ReportLogicalChange(identity=identity, title="auth")],
            claims=[
                Claim(
                    id=uuid4(),
                    change_id=identity.id,
                    kind=ClaimKind.OBSERVATION,
                    statement="cited",
                    evidence_ids=[uuid4()],
                    assessment=ClaimAssessment.SUPPORTED,
                )
            ],
            provenance=ReportProvenance(run_id=uuid4()),
        )


def test_assemble_rejects_mismatched_evidence_snapshot() -> None:
    report = _report()
    broken = report.model_copy(deep=True)
    object.__setattr__(
        broken.evidence[0],
        "snapshot_id",
        uuid4(),
    )
    with pytest.raises(ReportAssemblyError, match="snapshot_id"):
        assemble_analysis_report(broken)


def test_legacy_semantic_result_still_ignores_unknown_fields() -> None:
    result = SemanticAnalysisResult.model_validate(
        {"pr_intent": "keep owners", "unknown_field": True, "changes": []}
    )
    assert result.pr_intent == "keep owners"


def test_existing_analysis_result_constructor_unchanged() -> None:
    result = AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="abc",
            additions=1,
            deletions=0,
        ),
        changes=[LogicalChange(id="C1", title="auth")],
    )
    assert result.changes[0].id == "C1"


def test_v2_provider_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AnalysisResponse.model_validate({"kind": "result", "extra": 1})
    with pytest.raises(ValidationError):
        ContextRequest.model_validate({"kind": "needs_context", "requests": [], "hack": True})


def test_context_request_rejects_absolute_and_empty() -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest(reason="why", path="/etc/passwd")
    with pytest.raises(ValidationError):
        RetrievalRequest(reason="why")
    item = RetrievalRequest(reason="callers", symbol="delete_user")
    assert item.symbol == "delete_user"


def test_supported_claim_is_not_proven() -> None:
    report = _report()
    claim = report.claims[0]
    assert claim.assessment == ClaimAssessment.SUPPORTED
    assert "not truth" in claim.limitations[0]
