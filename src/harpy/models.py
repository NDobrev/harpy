"""Typed domain models. Scoring and the TUI operate on these only."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
