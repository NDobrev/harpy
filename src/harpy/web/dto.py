"""HTTP/DTO contracts for the browser workspace."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harpy.models import RepoPath, ReviewStatus, Sha256, UtcDateTime

SCOPE_IDS: tuple[str, ...] = (
    "changes",
    "api",
    "db",
    "security",
    "questions",
    "tests",
    "omissions",
    "diagrams",
)
CALL_SCOPE_IDS: tuple[str, ...] = tuple(
    scope_id for scope_id in SCOPE_IDS if scope_id != "diagrams"
)
NOTE_MAX_CHARS = 20_000
NOTE_MAX_BYTES = 80_000
SEARCH_MAX_CHARS = 256


class StrictWebModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeploymentMode(StrEnum):
    LOCAL = "local"
    SELF_HOSTED = "self_hosted"
    SAAS = "saas"


class MembershipRole(StrEnum):
    ADMINISTRATOR = "administrator"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class ThemeId(StrEnum):
    WHITE = "white"
    BLACK = "black"
    DARK_BLUE = "dark_blue"


class InboxTab(StrEnum):
    LOCAL = "local"
    AUTHORED = "authored"
    ASSIGNED = "assigned"
    REVIEW_REQUESTED = "review-requested"
    TRACKED = "tracked"


class TargetKind(StrEnum):
    GITHUB_PR = "github_pr"
    LOCAL_COMMITTED = "local_committed"
    LOCAL_STAGED = "local_staged"
    LOCAL_WORKING_TREE = "local_working_tree"


class ReportKind(StrEnum):
    STATIC = "static"
    SEMANTIC = "semantic"
    PARTIAL = "partial"
    LEGACY = "legacy"


class FreshnessId(StrEnum):
    CHECKING = "checking"
    CURRENT = "current"
    CODE_CHANGED = "code_changed"
    INTENT_CHANGED = "intent_changed"
    CODE_AND_INTENT_CHANGED = "code_and_intent_changed"
    UNKNOWN = "unknown"
    LOCAL_CHANGED = "local_changed"


class JobKind(StrEnum):
    ACQUIRE = "acquire"
    REFRESH = "refresh"
    ANALYZE = "analyze"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPhase(StrEnum):
    WAITING = "waiting"
    RESOLVING_TARGET = "resolving_target"
    FETCHING = "fetching"
    CAPTURING = "capturing"
    STATIC_ANALYSIS = "static_analysis"
    PREPARING = "preparing"
    ANALYZING = "analyzing"
    VALIDATING = "validating"
    PERSISTING = "persisting"
    STOPPING = "stopping"
    FINISHED = "finished"


class ScopeRunStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ScopeProvenance(StrEnum):
    NEW = "new"
    REUSED = "reused"
    LEGACY = "legacy"


class WebRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AvailabilityReason(StrEnum):
    MISSING_SNAPSHOT = "missing_snapshot"
    ABSENT_SIDE = "absent_side"
    BINARY = "binary"
    SYMLINK = "symlink"
    SUBMODULE = "submodule"
    UNSUPPORTED_ENCODING = "unsupported_encoding"
    SIZE_LIMIT = "size_limit"
    LEGACY_UNVERIFIED = "legacy_unverified"
    CORRUPT = "corrupt"
    MISSING_ARTIFACT = "missing_artifact"


class CompletenessStatus(StrEnum):
    STATIC = "static"
    PARTIAL = "partial"
    COMPLETE = "complete"
    LEGACY = "legacy"


class LensId(StrEnum):
    OVERVIEW = "overview"
    DIFF = "diff"
    BEHAVIOR = "behavior"
    TESTS = "tests"
    IMPACT = "impact"
    QUESTIONS = "questions"
    OMISSIONS = "omissions"
    HISTORY = "history"


class FocusedRegion(StrEnum):
    CHANGES = "changes"
    EVIDENCE = "evidence"
    INSPECTOR = "inspector"


class SourceSide(StrEnum):
    BASE = "base"
    HEAD = "head"


class DiffMode(StrEnum):
    FOCUSED = "focused"
    FULL = "full"
    PATCH = "patch"


class CopyMode(StrEnum):
    PATCH = "patch"
    BASE = "base"
    HEAD = "head"


class ClientKind(StrEnum):
    WEB = "web"
    TUI = "tui"


class EventType(StrEnum):
    JOB_UPDATED = "job.updated"
    REPORT_CREATED = "report.created"
    REVIEW_OBSERVED = "review.observed"
    DECISION_UPDATED = "decision.updated"
    NOTE_UPDATED = "note.updated"
    INBOX_UPDATED = "inbox.updated"
    ACCESS_CHANGED = "access.changed"
    RESYNC_REQUIRED = "resync_required"


class TokenSource(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class OpenTargetState(StrEnum):
    READY = "ready"
    QUEUED = "queued"


class ClaimKind(StrEnum):
    OBSERVATION = "observation"
    INFERENCE = "inference"
    QUESTION = "question"


class ClaimAssessment(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    UNSUPPORTED = "unsupported"


class EvidenceAssessment(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    UNSUPPORTED = "unsupported"


class DiagramKind(StrEnum):
    SCHEMA = "schema"
    SEQUENCE = "sequence"
    FLOW = "flow"
    TREE = "tree"


class SchemaChangeMarker(StrEnum):
    ADDED = "added"
    DROPPED = "dropped"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class ActorSummary(StrictWebModel):
    user_id: UUID
    display_name: str


class Capabilities(StrictWebModel):
    read: bool
    write_review_state: bool
    start_analysis: bool
    cancel_job: bool
    register_repository: bool


class VersionInfo(StrictWebModel):
    application: str
    api_schema_hash: str
    frontend_asset_hash: str | None = None


class MeUser(StrictWebModel):
    id: UUID
    display_name: str


class MembershipSummary(StrictWebModel):
    tenant_id: UUID
    slug: str
    name: str
    role: MembershipRole


class Me(StrictWebModel):
    user: MeUser
    memberships: list[MembershipSummary]
    mode: DeploymentMode
    csrf_token: str
    session_expires_at: UtcDateTime
    version_info: VersionInfo
    capabilities: Capabilities


class ScopeSelection(StrictWebModel):
    enabled: dict[str, bool]
    models: dict[str, str]
    preset: str | None = None

    @model_validator(mode="after")
    def _require_all_scope_ids(self) -> Self:
        if set(self.enabled) != set(SCOPE_IDS):
            raise ValueError("enabled must include all eight scope IDs")
        if set(self.models) != set(CALL_SCOPE_IDS):
            raise ValueError("models must include all seven nonmodifier scope IDs")
        return self


class ScopeAssessment(StrictWebModel):
    scope_id: str
    status: ScopeRunStatus
    model: str | None = None
    completed_at: UtcDateTime | None = None
    limitations: list[str] = Field(default_factory=list)
    provenance: ScopeProvenance
    source_report_id: UUID | None = None


class PlannedCall(StrictWebModel):
    id: str
    model: str
    scope_ids: list[str]
    stage: int
    context_name: str


class RevisionObservation(StrictWebModel):
    head_sha: str | None = None
    local_digest: Sha256 | None = None
    intent_digest: Sha256 | None = None
    base_tip_sha: str | None = None
    observed_at: UtcDateTime
    freshness: FreshnessId
    error_code: str | None = None


class ReviewProgress(StrictWebModel):
    reviewed: int
    question: int
    blocker: int
    unreviewed: int
    total: int
    report_id: UUID

    @model_validator(mode="after")
    def _counts_sum(self) -> Self:
        counted = self.reviewed + self.question + self.blocker + self.unreviewed
        if counted != self.total:
            raise ValueError("progress counts must sum to total")
        return self


class Completeness(StrictWebModel):
    assessed_scopes: int
    requested_scopes: int
    status: CompletenessStatus


class CoverageRange(StrictWebModel):
    side: SourceSide
    start_line: int
    end_line: int

    @model_validator(mode="after")
    def _inclusive(self) -> Self:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("coverage range must be inclusive and 1-based")
        return self


class CoverageEntry(StrictWebModel):
    hunk_id: str
    file_id: UUID
    owner_change_ids: list[UUID]
    supplied_ranges: list[CoverageRange] = Field(default_factory=list)
    omitted_ranges: list[CoverageRange] = Field(default_factory=list)
    truncated: bool
    exclusion_reason: str | None = None


class CoverageTotals(StrictWebModel):
    inventory_hunks: int
    accounted_hunks: int
    supplied_hunks: int
    omitted_hunks: int
    truncated_hunks: int
    unclassified_hunks: int


class Availability(StrictWebModel):
    available: bool
    reason: AvailabilityReason | None = None
    explanation: str | None = None


class NavigationSelection(StrictWebModel):
    change_id: UUID | None = None
    file_id: UUID | None = None
    lens: LensId = LensId.OVERVIEW
    focused_region: FocusedRegion = FocusedRegion.CHANGES
    side: SourceSide = SourceSide.HEAD
    line: int | None = None
    scroll_anchor: str | None = None
    scroll_offset: int = 0
    query: str = ""
    hide_noise: bool = False

    @model_validator(mode="after")
    def _bounds(self) -> Self:
        if self.line is not None and self.line < 1:
            raise ValueError("line must be a positive integer")
        if self.scroll_offset < 0:
            raise ValueError("scroll_offset must be nonnegative")
        if len(self.query) > SEARCH_MAX_CHARS:
            raise ValueError("query exceeds 256 characters")
        return self


class PersonalHistoryEntry(StrictWebModel):
    report_id: UUID
    change_id: UUID | None = None
    file_id: UUID | None = None
    lens: LensId
    side: SourceSide
    line: int | None = None
    scroll_anchor: str | None = None
    scroll_offset: int = 0


class SourceEvidence(StrictWebModel):
    id: UUID
    repository_id: UUID
    snapshot_id: UUID
    file_id: UUID
    side: SourceSide
    path: RepoPath
    blob_digest: Sha256
    start_line: int
    end_line: int
    excerpt: str
    excerpt_digest: Sha256
    assessment: EvidenceAssessment
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("evidence range must be inclusive and 1-based")
        return self


class Claim(StrictWebModel):
    id: UUID
    change_id: UUID
    kind: ClaimKind
    statement: str
    consequence: str | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    assessment: ClaimAssessment
    limitations: list[str] = Field(default_factory=list)


class SafeJobError(StrictWebModel):
    code: str
    message: str
    retryable: bool
    provider_call_started: bool
    request_id: str | None = None


class UsageReceipt(StrictWebModel):
    duration_seconds: float | None = None
    calls: int = 0
    repairs: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_source: TokenSource = TokenSource.UNAVAILABLE
    cost: None = None

    @model_validator(mode="after")
    def _nonnegative(self) -> Self:
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("duration_seconds must be nonnegative")
        if self.calls < 0 or self.repairs < 0:
            raise ValueError("call and repair counts must be nonnegative")
        return self


class FieldError(StrictWebModel):
    field: str
    message: str


class ErrorDetails(StrictWebModel):
    fields: list[FieldError] = Field(default_factory=list)


class ApiError(StrictWebModel):
    code: str
    message: str
    request_id: str
    retryable: bool
    details: ErrorDetails | None = None


class ErrorResponse(StrictWebModel):
    error: ApiError


class Page[ItemT](StrictWebModel):
    items: list[ItemT]
    next_cursor: str | None = None
    as_of: UtcDateTime
    truncated: bool | None = None
    warnings: list[str] = Field(default_factory=list)


class LocalAuthRequest(StrictWebModel):
    token: str


class RegisterLocalRepositoryRequest(StrictWebModel):
    path: str


class RegisterGithubRepositoryRequest(StrictWebModel):
    locator: str


class InboxRefreshRequest(StrictWebModel):
    tab: InboxTab
    open_only: bool = True


class OpenTargetRequest(StrictWebModel):
    repository_id: UUID
    kind: TargetKind
    acquire_latest: bool = False
    pr_number: int | None = None
    base_ref: str | None = None
    include_untracked: bool | None = None

    @model_validator(mode="after")
    def _kind_fields(self) -> Self:
        if self.kind is TargetKind.GITHUB_PR:
            if self.pr_number is None or self.pr_number < 1:
                raise ValueError("github_pr requires a positive pr_number")
            return self
        if self.pr_number is not None:
            raise ValueError("local comparisons do not accept pr_number")
        if self.kind is TargetKind.LOCAL_COMMITTED and not self.base_ref:
            raise ValueError("local_committed requires base_ref")
        if self.kind is TargetKind.LOCAL_WORKING_TREE and self.include_untracked is None:
            raise ValueError("local_working_tree requires include_untracked")
        if self.kind is TargetKind.LOCAL_STAGED and self.include_untracked is not None:
            raise ValueError("local_staged does not accept include_untracked")
        return self


class JobView(StrictWebModel):
    job_id: UUID
    kind: JobKind
    status: JobStatus
    phase: JobPhase
    review_id: UUID | None = None
    snapshot_id: UUID | None = None
    actor: ActorSummary
    scope_statuses: list[ScopeAssessment] = Field(default_factory=list)
    started_at: UtcDateTime | None = None
    ended_at: UtcDateTime | None = None
    cancel_requested: bool = False
    result_report_id: UUID | None = None
    result_repository_id: UUID | None = None
    error: SafeJobError | None = None
    usage: UsageReceipt | None = None
    last_sequence: int
    pr_number: int | None = None


class OpenTargetReady(StrictWebModel):
    state: Literal[OpenTargetState.READY] = OpenTargetState.READY
    review_id: UUID
    report_id: UUID
    navigation_url: str


class OpenTargetQueued(StrictWebModel):
    state: Literal[OpenTargetState.QUEUED] = OpenTargetState.QUEUED
    review_id: UUID
    job: JobView
    navigation_url: str


OpenTargetResponse = Annotated[OpenTargetReady | OpenTargetQueued, Field(discriminator="state")]


class ReviewTarget(StrictWebModel):
    kind: TargetKind
    pr_number: int | None = None
    label: str


class ReportSummary(StrictWebModel):
    report_id: UUID
    review_id: UUID
    snapshot_id: UUID
    kind: ReportKind
    created_at: UtcDateTime
    analyzed_revision: str | None = None
    scope_statuses: list[ScopeAssessment] = Field(default_factory=list)
    completeness: Completeness
    limitations: list[str] = Field(default_factory=list)
    change_count: int
    hunk_count: int


class ReviewSummary(StrictWebModel):
    review_id: UUID
    repository_id: UUID
    target: ReviewTarget
    title: str
    author: str | None = None
    pr_state: str | None = None
    updated_at: UtcDateTime | None = None
    latest_observation: RevisionObservation | None = None
    latest_report: ReportSummary | None = None
    review_progress: ReviewProgress | None = None
    capabilities: Capabilities


class ReportDetail(ReportSummary):
    freshness: RevisionObservation
    lens_availability: dict[str, Availability]
    snapshot_base_tip_sha: str | None = None
    snapshot_head_sha: str | None = None
    snapshot_local_digest: Sha256 | None = None


class ChangeSummary(StrictWebModel):
    change_id: UUID
    local_id: str
    title: str
    rank_index: int
    importance: float
    unexpectedness: float
    confidence: float
    risk: WebRisk
    file_count: int
    hunk_count: int
    noise: bool
    status: ReviewStatus
    decision_version: int
    note_present: bool


class DecisionResource(StrictWebModel):
    status: ReviewStatus
    version: int
    updated_at: UtcDateTime | None = None
    updated_by: ActorSummary | None = None


class NoteResource(StrictWebModel):
    text: str
    version: int
    updated_at: UtcDateTime | None = None
    updated_by: ActorSummary | None = None

    @model_validator(mode="after")
    def _note_bounds(self) -> Self:
        _validate_note(self.text)
        return self


class ChangeDetail(ChangeSummary):
    before: str | None = None
    after: str | None = None
    why: str | None = None
    consequence: str | None = None
    paths: list[RepoPath] = Field(default_factory=list)
    file_ids: list[UUID] = Field(default_factory=list)
    hunk_ids: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    impact_ids: list[UUID] = Field(default_factory=list)
    scope_limitations: list[str] = Field(default_factory=list)
    decision: DecisionResource
    note: NoteResource


class DiffRow(StrictWebModel):
    row_id: str
    kind: Literal["context", "addition", "deletion"]
    base_line: int | None = None
    head_line: int | None = None
    text: str
    continuation: bool = False
    hunk_id: str | None = None
    owner_change_ids: list[UUID] = Field(default_factory=list)


class DiffPage(StrictWebModel):
    report_id: UUID
    file_id: UUID
    mode: DiffMode
    rows: list[DiffRow]
    next_cursor: str | None = None
    limitations: list[str] = Field(default_factory=list)


class SourceLine(StrictWebModel):
    number: int
    text: str
    continuation_offset: int = 0
    continuation: bool = False


class SourcePage(StrictWebModel):
    snapshot_id: UUID
    file_id: UUID
    side: SourceSide
    blob_digest: Sha256 | None = None
    available: bool
    reason: AvailabilityReason | None = None
    start_line: int
    lines: list[SourceLine] = Field(default_factory=list)
    next_cursor: str | None = None


class AnalysisPlanView(StrictWebModel):
    plan_id: UUID
    review_id: UUID
    report_id: UUID
    snapshot_id: UUID
    digest: Sha256
    selection: ScopeSelection
    calls: list[PlannedCall]
    call_count: int
    expires_at: UtcDateTime
    warnings: list[str] = Field(default_factory=list)
    rerun_selected: bool = True


class PersonalSession(StrictWebModel):
    review_id: UUID
    client_kind: ClientKind
    report_id: UUID | None = None
    selection: NavigationSelection
    history: list[PersonalHistoryEntry] = Field(default_factory=list)
    version: int


class Event(StrictWebModel):
    sequence: int
    type: EventType
    created_at: UtcDateTime
    review_id: UUID | None = None
    report_id: UUID | None = None
    job_id: UUID | None = None
    resource_version: int | None = None
    data: dict[str, str | int | bool | None] = Field(default_factory=dict)


class SetDecisionRequest(StrictWebModel):
    status: ReviewStatus
    expected_version: int = Field(ge=0)


class SaveNoteRequest(StrictWebModel):
    text: str
    expected_version: int = Field(ge=0)

    @model_validator(mode="after")
    def _note_bounds(self) -> Self:
        _validate_note(self.text)
        return self


class CreatePlanRequest(StrictWebModel):
    report_id: UUID
    selection: ScopeSelection


class StartRunRequest(StrictWebModel):
    plan_id: UUID
    digest: Sha256
    acknowledge_historical_snapshot: bool = False


class Preferences(StrictWebModel):
    theme: ThemeId = ThemeId.DARK_BLUE
    code_font_size: int = 13
    wrap_lines: bool = False
    disabled_repositories: list[UUID] = Field(default_factory=list)
    folded_repositories: list[UUID] = Field(default_factory=list)
    last_scope_selection: ScopeSelection | None = None
    version: int = 0


class PatchPreferencesRequest(StrictWebModel):
    expected_version: int = Field(ge=0)
    theme: ThemeId | None = None
    code_font_size: int | None = None
    wrap_lines: bool | None = None
    disabled_repositories: list[UUID] | None = None
    folded_repositories: list[UUID] | None = None
    last_scope_selection: ScopeSelection | None = None


class Preset(StrictWebModel):
    preset_id: str
    name: str
    builtin: bool
    selection: ScopeSelection
    version: int


class CreatePresetRequest(StrictWebModel):
    name: str
    selection: ScopeSelection

    @field_validator("name")
    @classmethod
    def _name_bounds(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed or len(trimmed) > 80:
            raise ValueError("preset name must be 1-80 characters after trimming")
        return trimmed


class ReplacePresetRequest(StrictWebModel):
    name: str
    selection: ScopeSelection
    expected_version: int = Field(ge=0)


class SaveSessionRequest(StrictWebModel):
    client_kind: ClientKind
    report_id: UUID | None = None
    selection: NavigationSelection
    history: list[PersonalHistoryEntry] = Field(default_factory=list)
    expected_version: int = Field(ge=0)


class DiagramSourceTarget(StrictWebModel):
    file_id: UUID
    side: SourceSide
    line: int | None = None
    evidence_id: UUID | None = None


class SchemaColumn(StrictWebModel):
    id: str
    name: str
    type: str | None = None
    nullable: bool | None = None
    default: str | None = None
    primary_key: bool = False
    change: SchemaChangeMarker = SchemaChangeMarker.UNCHANGED


class SchemaRelation(StrictWebModel):
    id: str
    from_table_id: str
    from_column_id: str
    to_table_id: str
    to_column_id: str
    change: SchemaChangeMarker = SchemaChangeMarker.UNCHANGED


class SchemaTable(StrictWebModel):
    id: str
    name: str
    columns: list[SchemaColumn] = Field(default_factory=list)
    change: SchemaChangeMarker = SchemaChangeMarker.UNCHANGED


class SchemaDiagram(StrictWebModel):
    id: UUID
    kind: Literal[DiagramKind.SCHEMA] = DiagramKind.SCHEMA
    title: str
    explanation: str
    source_targets: list[DiagramSourceTarget] = Field(default_factory=list)
    old_tables: list[SchemaTable] = Field(default_factory=list)
    new_tables: list[SchemaTable] = Field(default_factory=list)
    relations: list[SchemaRelation] = Field(default_factory=list)


class SequenceActor(StrictWebModel):
    id: str
    label: str


class SequenceStep(StrictWebModel):
    id: str
    from_actor_id: str
    to_actor_id: str
    label: str
    branch_label: str | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)


class SequenceDiagram(StrictWebModel):
    id: UUID
    kind: Literal[DiagramKind.SEQUENCE] = DiagramKind.SEQUENCE
    title: str
    explanation: str
    source_targets: list[DiagramSourceTarget] = Field(default_factory=list)
    actors: list[SequenceActor]
    steps: list[SequenceStep]


class FlowNode(StrictWebModel):
    id: str
    label: str
    source_targets: list[DiagramSourceTarget] = Field(default_factory=list)


class FlowEdge(StrictWebModel):
    id: str
    from_node_id: str
    to_node_id: str
    label: str
    evidence_ids: list[UUID] = Field(default_factory=list)


class FlowDiagram(StrictWebModel):
    id: UUID
    kind: Literal[DiagramKind.FLOW] = DiagramKind.FLOW
    title: str
    explanation: str
    source_targets: list[DiagramSourceTarget] = Field(default_factory=list)
    nodes: list[FlowNode]
    edges: list[FlowEdge]

    @model_validator(mode="after")
    def _endpoints_exist(self) -> Self:
        known = {node.id for node in self.nodes}
        for edge in self.edges:
            if edge.from_node_id not in known or edge.to_node_id not in known:
                raise ValueError("flow edge endpoints must exist")
        return self


class TreeNode(StrictWebModel):
    id: str
    label: str
    kind: str
    source_targets: list[DiagramSourceTarget] = Field(default_factory=list)
    children: list[TreeNode] = Field(default_factory=list)
    reference_id: str | None = None


class TreeDiagram(StrictWebModel):
    id: UUID
    kind: Literal[DiagramKind.TREE] = DiagramKind.TREE
    title: str
    explanation: str
    source_targets: list[DiagramSourceTarget] = Field(default_factory=list)
    root: TreeNode


Diagram = Annotated[
    SchemaDiagram | SequenceDiagram | FlowDiagram | TreeDiagram,
    Field(discriminator="kind"),
]


class Impact(StrictWebModel):
    id: UUID
    kind: Literal["api", "db"]
    change_ids: list[UUID]
    title: str
    target: str
    before: str
    after: str
    breaking: bool | None = None
    business_logic: bool
    security: bool
    file_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    diagrams: list[Diagram] = Field(default_factory=list)


class RepositorySummary(StrictWebModel):
    repository_id: UUID
    kind: Literal["github", "local"]
    display_name: str
    capabilities: Capabilities


class ReviewDetail(StrictWebModel):
    review_id: UUID
    repository_id: UUID
    target: ReviewTarget
    title: str
    latest_observation: RevisionObservation | None = None
    reports: list[ReportSummary] = Field(default_factory=list)
    capabilities: Capabilities


class CoveragePage(StrictWebModel):
    totals: CoverageTotals
    items: list[CoverageEntry]
    next_cursor: str | None = None
    as_of: UtcDateTime
    unassessed_scopes: list[str] = Field(default_factory=list)


class ReviewEvent(StrictWebModel):
    id: UUID
    kind: Literal["decision", "note"]
    actor: ActorSummary
    created_at: UtcDateTime
    resource_version: int
    before: dict[str, str | int | None]
    after: dict[str, str | int | None]


class AnalysisCatalogScope(StrictWebModel):
    scope_id: str
    label: str
    kind: Literal["call", "modifier"]
    description: str
    enabled_reason: str | None = None
    disabled_reason: str | None = None


class AnalysisCatalog(StrictWebModel):
    scopes: list[AnalysisCatalogScope]
    models: list[str]
    default_model: str
    builtins: list[Preset]


class MigrationWarning(StrictWebModel):
    warning_id: UUID
    kind: Literal["decision", "note", "conflict"]
    reason: str
    original_review_ref: str
    original_change_ref: str | None = None
    resolved: bool = False


class ResolveMigrationWarningRequest(StrictWebModel):
    report_id: UUID | None = None
    change_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=0)
    acknowledge_without_mapping: bool = False


def _validate_note(text: str) -> None:
    if len(text) > NOTE_MAX_CHARS:
        raise ValueError("note exceeds 20000 characters")
    if len(text.encode("utf-8")) > NOTE_MAX_BYTES:
        raise ValueError("note exceeds 80000 UTF-8 bytes")


CONTRACT_MODELS: tuple[type[StrictWebModel], ...] = (
    Me,
    Capabilities,
    OpenTargetRequest,
    OpenTargetReady,
    OpenTargetQueued,
    ReviewSummary,
    ReportSummary,
    ReportDetail,
    ChangeSummary,
    ChangeDetail,
    DiffPage,
    SourcePage,
    DecisionResource,
    NoteResource,
    AnalysisPlanView,
    JobView,
    PersonalSession,
    Event,
    ErrorResponse,
    ScopeSelection,
    ScopeAssessment,
    PlannedCall,
    RevisionObservation,
    ReviewProgress,
    CoverageTotals,
    CoverageEntry,
    Availability,
    NavigationSelection,
    PersonalHistoryEntry,
    SourceEvidence,
    Claim,
    SafeJobError,
    UsageReceipt,
    Impact,
    Preferences,
    Preset,
    AnalysisCatalog,
    CoveragePage,
    ReviewDetail,
    RepositorySummary,
)
