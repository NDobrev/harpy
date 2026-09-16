"""SQLAlchemy schema for tenant-aware web/shared review state."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

JSONType = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("state IN ('active','suspended','deleting')", name="ck_tenants_state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    authorization_version: Mapped[int] = mapped_column(BigInteger, default=1)
    limits: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    issuer: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        ForeignKeyConstraint(["user_id"], ["users.id"]),
        CheckConstraint(
            "role IN ('administrator','reviewer','viewer')", name="ck_memberships_role"
        ),
        CheckConstraint("state IN ('active','revoked')", name="ck_memberships_state"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "host",
            "provider_repository_id",
            name="uq_repositories_github",
        ),
        CheckConstraint("provider IN ('github','local')", name="ck_repositories_provider"),
        CheckConstraint("state IN ('active','disabled')", name="ck_repositories_state"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(Text)
    provider_repository_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(Text)
    local_registration_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(Text, default="active")
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RepositoryGrant(Base):
    __tablename__ = "repository_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["memberships.tenant_id", "memberships.user_id"]
        ),
        CheckConstraint("permission IN ('read','review')", name="ck_grants_permission"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    permission: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Credential(Base):
    __tablename__ = "credentials"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        CheckConstraint("kind IN ('github','analyzer')", name="ck_credentials_kind"),
        CheckConstraint("state IN ('active','revoked')", name="ck_credentials_state"),
        Index(
            "uq_credentials_github_active",
            "tenant_id",
            "owner_user_id",
            "provider_host",
            unique=True,
            sqlite_where=text("kind = 'github' AND state = 'active'"),
            postgresql_where=text("kind = 'github' AND state = 'active'"),
        ),
        Index(
            "uq_credentials_analyzer_active",
            "tenant_id",
            unique=True,
            sqlite_where=text("kind = 'analyzer' AND state = 'active'"),
            postgresql_where=text("kind = 'analyzer' AND state = 'active'"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    provider_host: Mapped[str] = mapped_column(Text)
    ciphertext: Mapped[str] = mapped_column(Text)
    nonce: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    state: Mapped[str] = mapped_column(Text, default="active")
    verified_login: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
        ),
        UniqueConstraint("tenant_id", "repository_id", "target_key", name="uq_reviews_target"),
        CheckConstraint(
            "target_kind IN ('github_pr','local_committed','local_staged','local_working_tree')",
            name="ck_reviews_target_kind",
        ),
        Index("ix_reviews_tenant_id", "tenant_id", "id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid)
    target_kind: Mapped[str] = mapped_column(Text)
    target_key: Mapped[str] = mapped_column(Text)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_spec: Mapped[dict[str, object] | None] = mapped_column(JSONType, nullable=True)
    latest_report_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    last_observation: Mapped[dict[str, object] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "review_id"], ["reviews.tenant_id", "reviews.id"]),
        CheckConstraint(
            "acquisition_status IN ('complete','limited','legacy')",
            name="ck_snapshots_status",
        ),
        CheckConstraint(
            "acquisition_status = 'legacy' OR head_sha IS NOT NULL OR local_digest IS NOT NULL",
            name="ck_snapshots_identity",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(Uuid)
    base_tip_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_base_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent_digest: Mapped[str] = mapped_column(Text)
    manifest_digest: Mapped[str] = mapped_column(Text)
    diff_digest: Mapped[str] = mapped_column(Text)
    acquisition_status: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SnapshotFile(Base):
    __tablename__ = "snapshot_files"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "snapshot_id"], ["snapshots.tenant_id", "snapshots.id"]),
        UniqueConstraint("tenant_id", "snapshot_id", "path", name="uq_snapshot_files_path"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    path: Mapped[str] = mapped_column(Text)
    old_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text, default="")
    base_artifact: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_artifact: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_available: Mapped[bool] = mapped_column(Boolean, default=True)
    head_available: Mapped[bool] = mapped_column(Boolean, default=True)
    availability_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    binary: Mapped[bool] = mapped_column(Boolean, default=False)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "review_id"], ["reviews.tenant_id", "reviews.id"]),
        ForeignKeyConstraint(["tenant_id", "snapshot_id"], ["snapshots.tenant_id", "snapshots.id"]),
        CheckConstraint("kind IN ('static','semantic','partial','legacy')", name="ck_reports_kind"),
        Index("ix_reports_tenant_review", "tenant_id", "review_id"),
        Index("ix_reports_tenant_id", "tenant_id", "id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(Uuid)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(Integer)
    content_digest: Mapped[str] = mapped_column(Text)
    config_digest: Mapped[str] = mapped_column(Text)
    scope_summary: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    provenance: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LogicalChange(Base):
    __tablename__ = "logical_changes"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "review_id"], ["reviews.tenant_id", "reviews.id"]),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    lineage: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportChange(Base):
    __tablename__ = "report_changes"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "report_id"], ["reports.tenant_id", "reports.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "review_id", "change_id"],
            ["logical_changes.tenant_id", "logical_changes.review_id", "logical_changes.id"],
        ),
        UniqueConstraint("tenant_id", "report_id", "local_id", name="uq_report_changes_local"),
        Index("ix_report_changes_tenant_report", "tenant_id", "report_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    report_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    change_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(Uuid)
    local_id: Mapped[str] = mapped_column(Text)
    rank_index: Mapped[int] = mapped_column(Integer)
    projection: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "report_id", "change_id"],
            ["report_changes.tenant_id", "report_changes.report_id", "report_changes.change_id"],
        ),
        ForeignKeyConstraint(["tenant_id", "review_id"], ["reviews.tenant_id", "reviews.id"]),
        CheckConstraint(
            "status IN ('unreviewed','reviewed','question','blocker')",
            name="ck_decisions_status",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    report_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    change_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger)
    updated_by: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChangeNote(Base):
    __tablename__ = "change_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "report_id", "change_id"],
            ["report_changes.tenant_id", "report_changes.report_id", "report_changes.change_id"],
        ),
        ForeignKeyConstraint(["tenant_id", "review_id"], ["reviews.tenant_id", "reviews.id"]),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    report_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    change_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(Uuid)
    text: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger)
    updated_by: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        CheckConstraint("kind IN ('decision','note')", name="ck_review_events_kind"),
        Index("ix_review_events_tenant_review", "tenant_id", "review_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(Uuid)
    report_id: Mapped[UUID] = mapped_column(Uuid)
    change_id: Mapped[UUID] = mapped_column(Uuid)
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(Text)
    before_state: Mapped[dict[str, object]] = mapped_column("before", JSONType)
    after_state: Mapped[dict[str, object]] = mapped_column("after", JSONType)
    resource_version: Mapped[int] = mapped_column(BigInteger)
    correlation_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersonalSession(Base):
    __tablename__ = "personal_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "review_id"], ["reviews.tenant_id", "reviews.id"]),
        CheckConstraint("client_kind IN ('web','tui')", name="ck_sessions_client"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    client_kind: Mapped[str] = mapped_column(Text, primary_key=True)
    report_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    selection: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    history: Mapped[list[object]] = mapped_column(JSONType, default=list)
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Preference(Base):
    __tablename__ = "preferences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["memberships.tenant_id", "memberships.user_id"]
        ),
        CheckConstraint("theme IN ('white','black','dark_blue')", name="ck_preferences_theme"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    theme: Mapped[str] = mapped_column(Text, default="dark_blue")
    code_font_size: Mapped[int] = mapped_column(Integer, default=13)
    wrap_lines: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled_repositories: Mapped[list[object]] = mapped_column(JSONType, default=list)
    folded_repositories: Mapped[list[object]] = mapped_column(JSONType, default=list)
    last_scope_selection: Mapped[dict[str, object] | None] = mapped_column(JSONType, nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Preset(Base):
    __tablename__ = "presets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["memberships.tenant_id", "memberships.user_id"]
        ),
        UniqueConstraint("tenant_id", "user_id", "normalized_name", name="uq_presets_name"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text)
    selection: Mapped[dict[str, object]] = mapped_column(JSONType)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InboxCache(Base):
    __tablename__ = "inbox_cache"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        Index("ix_inbox_cache_user_tab", "tenant_id", "user_id", "tab"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tab: Mapped[str] = mapped_column(Text, primary_key=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    pr_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONType)
    credential_version: Mapped[int] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisPlan(Base):
    __tablename__ = "analysis_plans"
    __table_args__ = (ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),)

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid)
    review_id: Mapped[UUID] = mapped_column(Uuid)
    report_id: Mapped[UUID] = mapped_column(Uuid)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    selection: Mapped[dict[str, object]] = mapped_column(JSONType)
    calls: Mapped[list[object]] = mapped_column(JSONType)
    config_digest: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        CheckConstraint("kind IN ('acquire','refresh','analyze')", name="ck_jobs_kind"),
        CheckConstraint(
            "status IN ('queued','running','completed','partial','failed','cancelled')",
            name="ck_jobs_status",
        ),
        Index("ix_jobs_active", "tenant_id", "status", "created_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    review_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    snapshot_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(Text)
    plan_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    request_payload: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    dedupe_key: Mapped[str] = mapped_column(Text)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_generation: Mapped[int] = mapped_column(BigInteger, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    retry_of: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_report_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    result_repository_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    error: Mapped[dict[str, object] | None] = mapped_column(JSONType, nullable=True)
    usage: Mapped[dict[str, object] | None] = mapped_column(JSONType, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderInvocation(Base):
    __tablename__ = "provider_invocations"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "job_id"], ["jobs.tenant_id", "jobs.id"]),
        CheckConstraint(
            "state IN ('prepared','started','completed','failed','indeterminate')",
            name="ck_invocations_state",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    job_id: Mapped[UUID] = mapped_column(Uuid)
    call_id: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    request_digest: Mapped[str] = mapped_column(Text)
    result_artifact: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_session_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobScope(Base):
    __tablename__ = "job_scopes"
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "job_id"], ["jobs.tenant_id", "jobs.id"]),)

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    job_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    scope_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_artifact: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventCounter(Base):
    __tablename__ = "event_counters"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    last_sequence: Mapped[int] = mapped_column(BigInteger, default=0)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        CheckConstraint(
            "audience_kind IN ('user','repository','tenant')",
            name="ck_events_audience",
        ),
        Index("ix_events_tenant_sequence", "tenant_id", "sequence"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    audience_kind: Mapped[str] = mapped_column(Text)
    audience_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    review_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    report_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    job_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resource_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),)

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    route_key: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    request_digest: Mapped[str] = mapped_column(Text)
    response_status: Mapped[int] = mapped_column(Integer)
    response: Mapped[dict[str, object]] = mapped_column(JSONType)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),)

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    digest: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminAudit(Base):
    __tablename__ = "admin_audit"
    __table_args__ = (ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),)

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    actor_ref: Mapped[str] = mapped_column(Text)
    operation: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    redacted_detail: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MigrationImport(Base):
    __tablename__ = "migration_imports"

    import_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_fingerprint: Mapped[str] = mapped_column(Text)
    destination_tenant_id: Mapped[UUID] = mapped_column(Uuid)
    state: Mapped[str] = mapped_column(Text)
    counts: Mapped[dict[str, object]] = mapped_column(JSONType, default=dict)
    validation_digest: Mapped[str] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LegacyHumanWork(Base):
    __tablename__ = "legacy_human_work"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        CheckConstraint("kind IN ('decision','note','conflict')", name="ck_legacy_kind"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    import_id: Mapped[UUID] = mapped_column(Uuid)
    original_review_ref: Mapped[str] = mapped_column(Text)
    original_change_ref: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONType)
    reason: Mapped[str] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


TENANT_TABLES: tuple[str, ...] = (
    "memberships",
    "repositories",
    "repository_grants",
    "credentials",
    "reviews",
    "snapshots",
    "snapshot_files",
    "reports",
    "logical_changes",
    "report_changes",
    "decisions",
    "change_notes",
    "review_events",
    "personal_sessions",
    "preferences",
    "presets",
    "inbox_cache",
    "analysis_plans",
    "jobs",
    "provider_invocations",
    "job_scopes",
    "event_counters",
    "events",
    "idempotency_records",
    "artifacts",
    "admin_audit",
    "legacy_human_work",
)


def _install_immutability(connection: Connection) -> None:
    if connection.dialect.name == "sqlite":
        connection.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS reports_immutable "
                "BEFORE UPDATE ON reports BEGIN "
                "SELECT RAISE(ABORT, 'reports are immutable'); END;"
            )
        )
        return
    connection.execute(
        text(
            "CREATE OR REPLACE FUNCTION harpy_reject_report_update() "
            "RETURNS trigger AS $$ BEGIN "
            "RAISE EXCEPTION 'reports are immutable'; END; $$ LANGUAGE plpgsql;"
        )
    )
    connection.execute(text("DROP TRIGGER IF EXISTS reports_immutable ON reports"))
    connection.execute(
        text(
            "CREATE TRIGGER reports_immutable BEFORE UPDATE ON reports "
            "FOR EACH ROW EXECUTE FUNCTION harpy_reject_report_update()"
        )
    )


def _install_rls(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        connection.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        connection.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        connection.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
        connection.execute(
            text(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                "USING (tenant_id = NULLIF(current_setting('harpy.tenant_id', true), '')::uuid) "
                "WITH CHECK (tenant_id = NULLIF(current_setting('harpy.tenant_id', true), '')::uuid)"
            )
        )


def install_schema(connection: Connection) -> None:
    Base.metadata.create_all(connection)
    _install_immutability(connection)
    _install_rls(connection)
