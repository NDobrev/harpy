"""Typed domain models. Scoring and the TUI operate on these only."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AliasChoices, BaseModel, ConfigDict, Field, model_validator


class FileCategory(StrEnum):
    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    API = "API"
    AUTH = "AUTH"
    DATA = "DATA"
    CONFIG = "CONFIG"
    UI = "UI"
    TEST = "TEST"
    MIGRATION = "MIGRATION"
    GENERATED = "GENERATED"
    SNAPSHOT = "SNAPSHOT"
    LOCKFILE = "LOCKFILE"
    DOCUMENTATION = "DOCUMENTATION"
    BUILD = "BUILD"
    CI = "CI"
    UNKNOWN = "UNKNOWN"


class Risk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceType(StrEnum):
    STATIC_REFERENCE = "STATIC_REFERENCE"
    IMPORT = "IMPORT"
    ROUTE_MATCH = "ROUTE_MATCH"
    TEST_REFERENCE = "TEST_REFERENCE"
    CODEX_INFERENCE = "CODEX_INFERENCE"


class DiffHunk(BaseModel):
    id: str
    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    patch: str
    changed_symbols: list[str] = Field(default_factory=list)
    static_score: float = 0.0


class ChangedFile(BaseModel):
    path: str
    status: str
    additions: int
    deletions: int
    language: str | None = None
    generated_probability: float = 0.0
    test_probability: float = 0.0
    business_logic_probability: float = 0.0
    category_scores: dict[str, float] = Field(default_factory=dict)
    old_path: str | None = None
    is_binary: bool = False
    mode_change: bool = False
    is_submodule: bool = False
    hunks: list[DiffHunk] = Field(default_factory=list)


class PullRequest(BaseModel):
    number: int
    title: str
    body: str
    base_ref: str
    head_ref: str
    head_sha: str
    base_sha: str = ""
    additions: int
    deletions: int
    repo: str = ""
    state: str = ""
    files: list[ChangedFile] = Field(default_factory=list)


class SymbolFact(BaseModel):
    name: str
    kind: str = ""
    path: str = ""
    start_line: int = 0
    end_line: int = 0
    visibility: str = ""
    signature: str = ""


class ImportFact(BaseModel):
    path: str = ""
    line: int = 0
    module: str = ""
    names: list[str] = Field(default_factory=list)


class RouteFact(BaseModel):
    path: str = ""
    line: int = 0
    method: str = ""
    route: str = ""
    handler: str = ""


class DdlFact(BaseModel):
    path: str = ""
    line: int = 0
    operation: str = ""
    table: str = ""
    column: str = ""
    col_type: str = ""
    nullable: bool | None = None
    fk_table: str = ""
    fk_column: str = ""


class FileFacts(BaseModel):
    path: str = ""
    language: str = ""
    symbols: list[SymbolFact] = Field(default_factory=list)
    imports: list[ImportFact] = Field(default_factory=list)
    routes: list[RouteFact] = Field(default_factory=list)
    ddl: list[DdlFact] = Field(default_factory=list)

    def has_any(self) -> bool:
        return bool(self.symbols or self.imports or self.routes or self.ddl)


class ReferenceHit(BaseModel):
    symbol: str
    path: str
    line: int
    kind: str
    evidence: EvidenceType = EvidenceType.STATIC_REFERENCE
    snippet: str = ""


class StaticSignals(BaseModel):
    file_path: str
    hunk_id: str | None = None
    auth_change: bool = False
    api_change: bool = False
    db_change: bool = False
    migration: bool = False
    config_default: bool = False
    public_behavior: bool = False
    widely_referenced: bool = False
    error_handling: bool = False
    test_only: bool = False
    snapshot: bool = False
    generated: bool = False
    lockfile: bool = False
    raw_score: float = 0.0
    categories: list[str] = Field(default_factory=list)


class ScoringWeights(BaseModel):
    auth_change: float = 30
    public_behavior: float = 25
    db_change: float = 20
    api_change: float = 20
    migration: float = 15
    config_default: float = 15
    widely_referenced: float = 15
    error_handling: float = 10
    test_only: float = -10
    snapshot: float = -20
    generated: float = -30
    lockfile: float = -40
    behavior_weight: float = 0.25
    business_weight: float = 0.20
    blast_weight: float = 0.20
    security_weight: float = 0.15
    data_weight: float = 0.10
    novelty_weight: float = 0.10
    importance_mix: float = 0.7
    unexpectedness_mix: float = 0.3
    critical_boost: float = 15.0
    critical_threshold: float = 70.0


class LogicalChange(BaseModel):
    id: str
    title: str
    importance: float = 0.0
    confidence: float = 0.0
    unexpectedness: float = 0.0
    risk: str = Risk.LOW.value
    review_priority: float = 0.0
    business_impact: float = 0.0
    behavior_change: float = 0.0
    blast_radius: float = 0.0
    security_sensitivity: float = 0.0
    data_sensitivity: float = 0.0
    novelty: float = 0.0
    before: str = ""
    after: str = ""
    why: str = ""
    business_effect: str = ""
    files: list[str] = Field(default_factory=list)
    hunks: list[str] = Field(default_factory=list)
    hunk_ids: list[str] = Field(default_factory=list)
    affected_symbols: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)
    possible_omissions: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class SemanticChangeDraft(BaseModel):
    """Shape emitted by the analyzer before final scoring."""

    id: str
    title: str
    business_impact: float = 0
    behavior_change: float = 0
    blast_radius: float = 0
    security_sensitivity: float = 0
    data_sensitivity: float = 0
    novelty: float = 0
    confidence: float = 0
    unexpectedness: float = 0
    risk: str = "low"
    before: str = ""
    after: str = ""
    why: str = ""
    business_effect: str = ""
    files: list[str] = Field(default_factory=list)
    hunk_ids: list[str] = Field(default_factory=list)
    affected_symbols: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)
    possible_omissions: list[str] = Field(default_factory=list)


class SequenceStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_actor: str = Field(default="", validation_alias=AliasChoices("from_actor", "from"))
    to_actor: str = Field(default="", validation_alias=AliasChoices("to_actor", "to"))
    message: str = ""
    kind: str = "sync"
    change: str = ""
    path: str = ""
    symbol: str = ""


class SequenceDiagram(BaseModel):
    actors: list[str] = Field(default_factory=list)
    steps: list[SequenceStep] = Field(default_factory=list)


class FlowNode(BaseModel):
    id: str = ""
    label: str = ""
    shape: str = "process"
    change: str = ""
    path: str = ""


class FlowEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_id: str = Field(default="", validation_alias=AliasChoices("from_id", "from"))
    to_id: str = Field(default="", validation_alias=AliasChoices("to_id", "to"))
    label: str = ""
    change: str = ""


class FlowDiagram(BaseModel):
    nodes: list[FlowNode] = Field(default_factory=list)
    edges: list[FlowEdge] = Field(default_factory=list)


class BlastTreeNode(BaseModel):
    label: str = ""
    kind: str = ""
    evidence: str = ""
    path: str = ""
    line: int = 0
    children: list[BlastTreeNode] = Field(default_factory=list)


class BlastTree(BaseModel):
    root: BlastTreeNode = Field(default_factory=BlastTreeNode)


class DiagramHit(BaseModel):
    row: int
    col: int
    width: int
    node_id: str
    path: str = ""
    line: int = 0
    hunk_id: str = ""


class RenderedDiagram(BaseModel):
    title: str = ""
    kind: str
    lines: list[str] = Field(default_factory=list)
    hits: list[DiagramHit] = Field(default_factory=list)


class ApiDiagram(BaseModel):
    kind: str = "before_after"
    title: str = ""
    mermaid: str = ""
    why: str = ""
    sequence: SequenceDiagram | None = None
    flow: FlowDiagram | None = None
    tree: BlastTree | None = None


class SchemaColumn(BaseModel):
    name: str = ""
    type: str = ""
    old_type: str = ""
    nullable: bool = True
    pk: bool = False
    fk: str = ""
    fk_column: str = ""
    change: str = ""


class SchemaTable(BaseModel):
    name: str = ""
    change: str = ""
    columns: list[SchemaColumn] = Field(default_factory=list)


class SchemaRelation(BaseModel):
    from_table: str = ""
    to_table: str = ""
    from_column: str = ""
    to_column: str = ""
    label: str = ""
    change: str = ""


class SchemaSnapshot(BaseModel):
    tables: list[SchemaTable] = Field(default_factory=list)
    relations: list[SchemaRelation] = Field(default_factory=list)


class ApiEndpointImpact(BaseModel):
    change_id: str = ""
    method: str = ""
    path: str = ""
    summary: str = ""
    before: str = ""
    after: str = ""
    impact: str = ""
    breaking: bool = False
    breaking_reason: str = ""
    callers: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    business_logic: bool = False
    business_logic_why: str = ""
    security: bool = False
    security_why: str = ""
    diagrams: list[ApiDiagram] = Field(default_factory=list)
    sequence: SequenceDiagram | None = None
    flow: FlowDiagram | None = None
    tree: BlastTree | None = None


class DbChangeImpact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    change_id: str = ""
    operation: str = ""
    target: str = ""
    summary: str = ""
    before: str = ""
    after: str = ""
    impact: str = ""
    breaking: bool = False
    breaking_reason: str = ""
    objects: list[str] = Field(default_factory=list)
    schema_snapshot: SchemaSnapshot = Field(default_factory=SchemaSnapshot, alias="schema")
    files: list[str] = Field(default_factory=list)
    business_logic: bool = False
    business_logic_why: str = ""
    security: bool = False
    security_why: str = ""
    diagrams: list[ApiDiagram] = Field(default_factory=list)
    sequence: SequenceDiagram | None = None
    flow: FlowDiagram | None = None
    tree: BlastTree | None = None


class ChangeAnnotation(BaseModel):
    """Per-change fields emitted when a scope runs in a separate agent call."""

    change_id: str
    security_sensitivity: float | None = None
    data_sensitivity: float | None = None
    review_questions: list[str] | None = None
    tests: list[str] | None = None
    possible_omissions: list[str] | None = None


class ScopeSelection(BaseModel):
    enabled: dict[str, bool] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
    preset: str | None = None


class ScopePreset(BaseModel):
    name: str
    builtin: bool = False
    enabled: dict[str, bool] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)


class ScopeCall(BaseModel):
    id: str
    model: str
    scope_ids: list[str] = Field(default_factory=list)
    stage: int = 1
    context_name: str = ""


class SemanticAnalysisResult(BaseModel):
    pr_intent: str = ""
    changes: list[SemanticChangeDraft] = Field(default_factory=list)
    api_impacts: list[ApiEndpointImpact] = Field(default_factory=list)
    db_impacts: list[DbChangeImpact] = Field(default_factory=list)
    annotations: list[ChangeAnnotation] = Field(default_factory=list)
    degraded: bool = False
    error: str | None = None


class AnalysisResult(BaseModel):
    pr: PullRequest
    files: list[ChangedFile] = Field(default_factory=list)
    hunks: list[DiffHunk] = Field(default_factory=list)
    changes: list[LogicalChange] = Field(default_factory=list)
    signals: list[StaticSignals] = Field(default_factory=list)
    references: list[ReferenceHit] = Field(default_factory=list)
    semantic_available: bool = False
    banner: str | None = None
    pr_intent: str = ""
    workspace_path: str | None = None
    analysis_key: str = ""
    worktree_error: str | None = None
    pending_semantic: bool = False
    api_impacts: list[ApiEndpointImpact] = Field(default_factory=list)
    db_impacts: list[DbChangeImpact] = Field(default_factory=list)
    file_facts: list[FileFacts] = Field(default_factory=list)
    scopes_run: list[str] = Field(default_factory=list)
    scope_signature: str = ""


REPORT_SCHEMA_VERSION: Literal[2] = 2
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC)


def _require_sha256(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("expected SHA-256 hex digest")
    return value


def _require_repo_path(value: str) -> str:
    if not value or value.startswith("/") or "\\" in value:
        raise ValueError("path must be a repository-relative POSIX path")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("path must not contain empty, '.', or '..' segments")
    return value


def _require_optional_repo_path(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return _require_repo_path(value)


UtcDateTime = Annotated[datetime, AfterValidator(_require_utc)]
Sha256 = Annotated[str, AfterValidator(_require_sha256)]
RepoPath = Annotated[str, AfterValidator(_require_repo_path)]
OptionalRepoPath = Annotated[str | None, AfterValidator(_require_optional_repo_path)]


class StrictV2Model(BaseModel):
    """V2 records reject unknown fields. Legacy models keep tolerant parsing."""

    model_config = ConfigDict(extra="forbid")


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScopeStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ClaimKind(StrEnum):
    OBSERVATION = "observation"
    INFERENCE = "inference"
    QUESTION = "question"


class ClaimAssessment(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    UNSUPPORTED = "unsupported"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    QUESTION = "question"
    BLOCKER = "blocker"


class FindingDisposition(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    DEFERRED = "deferred"
    RESOLVED = "resolved"
    INCORRECT = "incorrect"
    DUPLICATE = "duplicate"
    IRRELEVANT = "irrelevant"


class RequirementAssessment(StrEnum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    DEFERRED = "deferred"


class Freshness(StrEnum):
    CHECKING = "checking"
    CURRENT = "current"
    CODE_CHANGED = "code_changed"
    INTENT_CHANGED = "intent_changed"
    CODE_AND_INTENT_CHANGED = "code_and_intent_changed"
    UNKNOWN = "unknown"
    LOCAL_CHANGED = "local_changed"


class LineRange(StrictV2Model):
    start_line: int
    end_line: int

    @model_validator(mode="after")
    def _inclusive_range(self) -> LineRange:
        if self.start_line < 1:
            raise ValueError("start_line must be >= 1")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class RepositoryIdentity(StrictV2Model):
    id: UUID
    provider: str
    host: str
    provider_repository_id: str | None = None
    display_name: str
    git_common_dir_id: str | None = None


class ReviewTarget(StrictV2Model):
    source_kind: str
    repository_id: UUID
    pr_number: int | None = None
    local_comparison: str | None = None


class FileManifestEntry(StrictV2Model):
    path: RepoPath
    old_path: OptionalRepoPath = None
    file_kind: str
    mode: str = ""
    base_blob: str | None = None
    head_blob: str | None = None
    binary: bool = False
    byte_size: int = 0
    source_available: bool = True


class RevisionSnapshot(StrictV2Model):
    id: UUID
    target_id: UUID
    base_tip_sha: str
    comparison_base_sha: str
    head_sha: str
    title: str = ""
    body: str = ""
    file_manifest: list[FileManifestEntry] = Field(default_factory=list)
    diff_digest: Sha256
    created_at: UtcDateTime
    acquisition_complete: bool = True


class UsageReceipt(StrictV2Model):
    duration_seconds: float | None = None
    calls: int = 0
    retries: int = 0
    supplied_context_estimate: int | None = None
    token_source: Literal["measured", "estimated", "unavailable"] = "unavailable"


class AnalysisRun(StrictV2Model):
    id: UUID
    snapshot_id: UUID
    scope_selection: ScopeSelection = Field(default_factory=ScopeSelection)
    execution_plan_digest: Sha256
    status: RunStatus
    started_at: UtcDateTime | None = None
    ended_at: UtcDateTime | None = None
    owner: str = ""
    progress: str = ""
    usage_receipt: UsageReceipt | None = None


class ScopeAssessment(StrictV2Model):
    scope_id: str
    status: ScopeStatus
    model: str = ""
    prompt_version: str = ""
    artifact_key: str = ""
    error_category: str | None = None
    completed_at: UtcDateTime | None = None
    reused_from: str | None = None


class LogicalChangeIdentity(StrictV2Model):
    id: UUID
    revision_local_ids: list[str] = Field(default_factory=list)
    fingerprints: list[Sha256] = Field(default_factory=list)
    predecessors: list[UUID] = Field(default_factory=list)
    successors: list[UUID] = Field(default_factory=list)


class SourceEvidence(StrictV2Model):
    id: UUID
    content_key: Sha256
    repository_id: UUID
    snapshot_id: UUID
    side: Literal["base", "head"]
    path: RepoPath
    blob_hash: Sha256
    start_line: int
    end_line: int
    excerpt: str
    excerpt_hash: Sha256
    source_kind: str

    @model_validator(mode="after")
    def _range(self) -> SourceEvidence:
        LineRange(start_line=self.start_line, end_line=self.end_line)
        return self


class Claim(StrictV2Model):
    id: UUID
    change_id: UUID
    kind: ClaimKind
    statement: str
    consequence: str = ""
    evidence_ids: list[UUID] = Field(default_factory=list)
    counterevidence_ids: list[UUID] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    scope: str = ""
    assessment: ClaimAssessment


class CoverageEntry(StrictV2Model):
    hunk_id: str
    primary_owner: str = ""
    secondary_owners: list[str] = Field(default_factory=list)
    supplied_ranges: list[LineRange] = Field(default_factory=list)
    truncated_ranges: list[LineRange] = Field(default_factory=list)
    omitted_ranges: list[LineRange] = Field(default_factory=list)
    exclusion_reason: str | None = None


class ReviewDecision(StrictV2Model):
    review_id: UUID
    change_id: UUID
    status: ReviewStatus
    report_id: UUID
    dependency_digest: Sha256
    note: str = ""
    decided_at: UtcDateTime


class FindingEvent(StrictV2Model):
    at: UtcDateTime
    disposition: FindingDisposition
    note: str = ""


class ReviewFinding(StrictV2Model):
    id: UUID
    claim_id: UUID | None = None
    change_id: UUID | None = None
    disposition: FindingDisposition
    note: str = ""
    resolution_evidence_ids: list[UUID] = Field(default_factory=list)
    history: list[FindingEvent] = Field(default_factory=list)


class Requirement(StrictV2Model):
    id: UUID
    source_document: str
    source_span: str = ""
    original_text: str
    change_ids: list[UUID] = Field(default_factory=list)
    scenario_ids: list[UUID] = Field(default_factory=list)
    test_ids: list[UUID] = Field(default_factory=list)
    assessment: RequirementAssessment


class Scenario(StrictV2Model):
    id: UUID
    actor: str
    input: str = ""
    preconditions: list[str] = Field(default_factory=list)
    before: str = ""
    after: str = ""
    side_effects: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    inferred: bool = True


class TestEvidence(StrictV2Model):
    identity: str
    language: str
    framework: str = ""
    assertion_locations: list[str] = Field(default_factory=list)
    behavior_mappings: list[str] = Field(default_factory=list)
    strength: str
    execution_refs: list[UUID] = Field(default_factory=list)


class VerificationRun(StrictV2Model):
    id: UUID
    snapshot_id: UUID
    profile: str
    image_digest: str
    command: list[str] = Field(default_factory=list)
    limits: dict[str, str] = Field(default_factory=dict)
    exit_status: int | None = None
    logs: str = ""
    parsed_results: dict[str, str] = Field(default_factory=dict)


class DraftComment(StrictV2Model):
    path: RepoPath
    side: Literal["base", "head"]
    start_line: int
    end_line: int
    body: str

    @model_validator(mode="after")
    def _range(self) -> DraftComment:
        LineRange(start_line=self.start_line, end_line=self.end_line)
        return self


class DraftReview(StrictV2Model):
    id: UUID
    snapshot_id: UUID
    review_event: str
    body: str = ""
    comments: list[DraftComment] = Field(default_factory=list)
    submission_state: str = "draft"


class NavigationState(StrictV2Model):
    review_id: UUID
    report_id: UUID | None = None
    selected_change: UUID | None = None
    lens: str = "overview"
    focused_pane: str = "navigator"
    pane_anchors: dict[str, str] = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list)


class ReportLogicalChange(StrictV2Model):
    identity: LogicalChangeIdentity
    title: str
    hunk_ids: list[str] = Field(default_factory=list)
    files: list[RepoPath] = Field(default_factory=list)


class ImpactRecord(StrictV2Model):
    kind: str
    summary: str
    change_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class DependencyManifest(StrictV2Model):
    source_files: dict[RepoPath, Sha256] = Field(default_factory=dict)
    syntax_query_results: list[Sha256] = Field(default_factory=list)
    reference_searches: list[Sha256] = Field(default_factory=list)
    negative_searches: list[Sha256] = Field(default_factory=list)
    intent_hashes: list[Sha256] = Field(default_factory=list)
    invariant_hashes: list[Sha256] = Field(default_factory=list)
    upstream_artifact_keys: list[str] = Field(default_factory=list)
    whole_tree: bool = False


class ReportProvenance(StrictV2Model):
    run_id: UUID
    schema_version: Literal[2] = REPORT_SCHEMA_VERSION
    reused_artifacts: list[str] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    legacy: bool = False


class AnalysisReport(StrictV2Model):
    id: UUID
    schema_version: Literal[2] = REPORT_SCHEMA_VERSION
    snapshot_id: UUID
    scope_results: list[ScopeAssessment] = Field(default_factory=list)
    logical_changes: list[ReportLogicalChange] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    impacts: list[ImpactRecord] = Field(default_factory=list)
    coverage: list[CoverageEntry] = Field(default_factory=list)
    evidence: list[SourceEvidence] = Field(default_factory=list)
    dependency_manifest: DependencyManifest = Field(default_factory=DependencyManifest)
    provenance: ReportProvenance

    @model_validator(mode="after")
    def _cross_record_ids(self) -> AnalysisReport:
        return _check_report_refs(self)


class ReportAssemblyError(ValueError):
    """Cross-record identifiers in a V2 report do not resolve."""


def _check_report_refs(report: AnalysisReport) -> AnalysisReport:
    change_ids = {change.identity.id for change in report.logical_changes}
    evidence_ids = {item.id for item in report.evidence}
    claim_ids = {claim.id for claim in report.claims}
    if len(change_ids) != len(report.logical_changes):
        raise ReportAssemblyError("duplicate logical change identity")
    if len(evidence_ids) != len(report.evidence):
        raise ReportAssemblyError("duplicate evidence id")
    if len(claim_ids) != len(report.claims):
        raise ReportAssemblyError("duplicate claim id")
    for item in report.evidence:
        if item.snapshot_id != report.snapshot_id:
            raise ReportAssemblyError("evidence snapshot_id does not match report")
    for claim in report.claims:
        if claim.change_id not in change_ids:
            raise ReportAssemblyError(f"claim {claim.id} references unknown change")
        for evidence_id in (*claim.evidence_ids, *claim.counterevidence_ids):
            if evidence_id not in evidence_ids:
                raise ReportAssemblyError(f"claim {claim.id} references unknown evidence")
    for impact in report.impacts:
        if any(change_id not in change_ids for change_id in impact.change_ids):
            raise ReportAssemblyError("impact references unknown change")
        if any(evidence_id not in evidence_ids for evidence_id in impact.evidence_ids):
            raise ReportAssemblyError("impact references unknown evidence")
    return report


class AnalysisResponse(StrictV2Model):
    kind: Literal["result"]
    scope_results: list[ScopeAssessment] = Field(default_factory=list)
    changes: list[ReportLogicalChange] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[SourceEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RetrievalRequest(StrictV2Model):
    reason: str
    path: OptionalRepoPath = None
    symbol: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    search: str | None = None

    @model_validator(mode="after")
    def _bounded(self) -> RetrievalRequest:
        if (self.start_line is None) != (self.end_line is None):
            raise ValueError("line range must include both start_line and end_line")
        if self.start_line is not None and self.end_line is not None:
            LineRange(start_line=self.start_line, end_line=self.end_line)
        if not (self.path or self.symbol or self.search):
            raise ValueError("request must name a path, symbol, or search")
        return self


class ContextRequest(StrictV2Model):
    kind: Literal["needs_context"]
    requests: list[RetrievalRequest] = Field(default_factory=list)


class ReportSummary(StrictV2Model):
    report_id: UUID
    snapshot_id: UUID
    created_at: UtcDateTime
    schema_version: Literal[2] = REPORT_SCHEMA_VERSION
    scope_completeness: str = ""
    freshness: Freshness = Freshness.UNKNOWN


class BrowserItem(BaseModel):
    review_id: UUID | None = None
    report_id: UUID | None = None
    tab: str = "local"
    repo: str = ""
    number: int | None = None
    title: str = ""
    author: str = ""
    source: str = "github"
    analyzed_rev: str = ""
    latest_rev: str = ""
    analyzed_at: str = ""
    updated_at: str = ""
    completeness: str = ""
    review_progress: str = ""
    freshness: Freshness = Freshness.UNKNOWN
    ci_summary: str = ""
    has_local_report: bool = False
    query_error: str = ""
    truncated: bool = False
    cached_at: str = ""
    pr_state: str = ""


class ReviewView(StrictV2Model):
    review_id: UUID
    target: ReviewTarget
    snapshot: RevisionSnapshot
    report: AnalysisReport | None = None
    freshness: Freshness = Freshness.UNKNOWN
    navigation: NavigationState | None = None


class RefreshResult(StrictV2Model):
    review_id: UUID
    freshness: Freshness
    latest_head: str
    analyzed_head: str | None = None


class ReviewPage(StrictV2Model):
    items: list[ReviewView] = Field(default_factory=list)
    next_cursor: str | None = None


class AnalysisPlan(StrictV2Model):
    id: UUID
    review_id: UUID
    snapshot_id: UUID
    full: bool = False
    reuse_count: int = 0
    reanalyze_count: int = 0
    new_count: int = 0
    reason: str = ""
    digest: Sha256


class RunHandle(StrictV2Model):
    run_id: UUID
    review_id: UUID
    snapshot_id: UUID
    status: RunStatus


class ProgressEvent(StrictV2Model):
    run_id: UUID
    review_id: UUID
    snapshot_id: UUID
    sequence: int
    status: RunStatus
    message: str = ""


class ChangeView(StrictV2Model):
    review_id: UUID
    report_id: UUID
    change: ReportLogicalChange
    claims: list[Claim] = Field(default_factory=list)


class EvidenceView(StrictV2Model):
    evidence: SourceEvidence


class SearchResult(StrictV2Model):
    kind: str
    title: str
    target_id: str
    score: float = 0.0


class ExportReceipt(StrictV2Model):
    path: str
    format: str
    report_id: UUID


class SubmissionPreview(StrictV2Model):
    digest: Sha256
    snapshot_id: UUID
    review_event: str
    body: str = ""
    comment_count: int = 0


class SubmissionReceipt(StrictV2Model):
    submission_id: UUID
    remote_id: str = ""
    url: str = ""


class VerificationPreview(StrictV2Model):
    digest: Sha256
    snapshot_id: UUID
    profile: str
    image_digest: str
    command: list[str] = Field(default_factory=list)


def assemble_analysis_report(report: AnalysisReport) -> AnalysisReport:
    """Reject reports whose claims, impacts, or evidence IDs do not resolve."""
    return _check_report_refs(report)
