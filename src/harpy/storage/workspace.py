"""Tenant-aware repositories for shared review state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from json import dumps
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from harpy.models import ReviewStatus
from harpy.storage.engine import set_tenant_guc
from harpy.storage.schema import (
    Artifact,
    ChangeNote,
    Credential,
    Decision,
    Event,
    EventCounter,
    IdempotencyRecord,
    InboxCache,
    Job,
    LogicalChange,
    Membership,
    PersonalSession,
    Report,
    ReportChange,
    Repository,
    RepositoryGrant,
    Review,
    ReviewEvent,
    Snapshot,
    Tenant,
    User,
    utcnow,
)
from harpy.storage.tenant_files import read_tenant_bytes, write_tenant_bytes

WRITE_ROLES = frozenset({"administrator", "reviewer"})
NOTE_MAX_CHARS = 20_000
NOTE_MAX_BYTES = 80_000
IDEMPOTENCY_TTL = timedelta(hours=24)


class WorkspaceError(RuntimeError):
    pass


class AccessDenied(WorkspaceError):
    pass


class NotFound(WorkspaceError):
    pass


class VersionConflict(WorkspaceError):
    def __init__(self, current: DecisionRecord | NoteRecord) -> None:
        super().__init__("version_conflict")
        self.current = current

    @property
    def note(self) -> NoteRecord:
        if not isinstance(self.current, NoteRecord):
            raise TypeError("conflict is not a note")
        return self.current

    @property
    def decision(self) -> DecisionRecord:
        if not isinstance(self.current, DecisionRecord):
            raise TypeError("conflict is not a decision")
        return self.current


class IdempotencyConflict(WorkspaceError):
    def __init__(self) -> None:
        super().__init__("idempotency_conflict")


@dataclass(frozen=True)
class ActorContext:
    tenant_id: UUID
    actor_id: UUID
    role: str
    correlation_id: UUID
    authorization_version: int


@dataclass(frozen=True)
class DecisionRecord:
    status: str
    version: int
    updated_at: datetime | None
    updated_by: UUID | None


@dataclass(frozen=True)
class NoteRecord:
    text: str
    version: int
    updated_at: datetime | None
    updated_by: UUID | None


@dataclass(frozen=True)
class ProgressRecord:
    reviewed: int
    question: int
    blocker: int
    unreviewed: int
    total: int
    report_id: UUID


@dataclass(frozen=True)
class DecisionMutation:
    value: DecisionRecord
    last_sequence: int
    replayed: bool = False


@dataclass(frozen=True)
class NoteMutation:
    value: NoteRecord
    last_sequence: int
    replayed: bool = False


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkspaceError("invalid idempotency payload")
    return value


def request_digest(payload: dict[str, object]) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def next_decision_status(current: str, action: str) -> str:
    if action == "reviewed":
        return ReviewStatus.REVIEWED.value
    if action == "reopen":
        return ReviewStatus.UNREVIEWED.value
    if action == "question":
        return ReviewStatus.QUESTION.value
    if action == "blocker":
        if current == ReviewStatus.BLOCKER.value:
            return ReviewStatus.UNREVIEWED.value
        return ReviewStatus.BLOCKER.value
    raise ValueError(f"unknown decision action: {action}")


class TenantWorkspace:
    def __init__(
        self,
        session: Session,
        context: ActorContext,
        *,
        artifact_root: Path | None = None,
    ) -> None:
        self.session = session
        self.context = context
        self.artifact_root = artifact_root
        set_tenant_guc(session, context.tenant_id)

    def _membership(self) -> Membership:
        membership = self.session.get(Membership, (self.context.tenant_id, self.context.actor_id))
        tenant = self.session.get(Tenant, self.context.tenant_id)
        if tenant is None or tenant.state != "active":
            raise AccessDenied("tenant unavailable")
        if (
            membership is None
            or membership.state != "active"
            or membership.version < 0
            or tenant.authorization_version < self.context.authorization_version
        ):
            raise AccessDenied("membership unavailable")
        return membership

    def _authorize_review_write(self, repository_id: UUID) -> None:
        membership = self._membership()
        if membership.role not in WRITE_ROLES:
            raise AccessDenied("role cannot mutate review state")
        grant = self.session.get(
            RepositoryGrant,
            (self.context.tenant_id, repository_id, self.context.actor_id),
        )
        if grant is None or grant.permission != "review":
            raise AccessDenied("repository grant required")

    def _report_change(self, report_id: UUID, change_id: UUID) -> ReportChange:
        row = self.session.get(ReportChange, (self.context.tenant_id, report_id, change_id))
        if row is None:
            raise NotFound("change not found")
        return row

    def _review_for_report(self, report_id: UUID) -> Review:
        report = self.session.get(Report, (self.context.tenant_id, report_id))
        if report is None:
            raise NotFound("report not found")
        review = self.session.get(Review, (self.context.tenant_id, report.review_id))
        if review is None:
            raise NotFound("review not found")
        return review

    def _idempotency(
        self,
        route_key: str,
        key: UUID,
        digest: str,
    ) -> dict[str, object] | None:
        row = self.session.get(
            IdempotencyRecord,
            (self.context.tenant_id, self.context.actor_id, route_key, key),
        )
        if row is None:
            return None
        if row.request_digest != digest:
            raise IdempotencyConflict()
        return row.response

    def _store_idempotency(
        self,
        route_key: str,
        key: UUID,
        digest: str,
        status: int,
        response: dict[str, object],
    ) -> None:
        self.session.merge(
            IdempotencyRecord(
                tenant_id=self.context.tenant_id,
                user_id=self.context.actor_id,
                route_key=route_key,
                key=key,
                request_digest=digest,
                response_status=status,
                response=response,
                expires_at=utcnow() + IDEMPOTENCY_TTL,
            )
        )

    def _next_sequence(self) -> int:
        counter = self.session.get(EventCounter, self.context.tenant_id)
        if counter is None:
            counter = EventCounter(tenant_id=self.context.tenant_id, last_sequence=0)
            self.session.add(counter)
            self.session.flush()
        counter.last_sequence += 1
        self.session.flush()
        return counter.last_sequence

    def _append_history(
        self,
        *,
        kind: str,
        review_id: UUID,
        report_id: UUID,
        change_id: UUID,
        before: dict[str, object],
        after: dict[str, object],
        resource_version: int,
        event_type: str,
    ) -> int:
        sequence = self._next_sequence()
        self.session.add(
            ReviewEvent(
                tenant_id=self.context.tenant_id,
                id=uuid4(),
                review_id=review_id,
                report_id=report_id,
                change_id=change_id,
                actor_id=self.context.actor_id,
                kind=kind,
                before_state=before,
                after_state=after,
                resource_version=resource_version,
                correlation_id=self.context.correlation_id,
            )
        )
        self.session.add(
            Event(
                tenant_id=self.context.tenant_id,
                sequence=sequence,
                type=event_type,
                audience_kind="repository",
                review_id=review_id,
                report_id=report_id,
                resource_version=resource_version,
                payload={"change_id": str(change_id), "kind": kind},
            )
        )
        return sequence

    def get_decision(self, report_id: UUID, change_id: UUID) -> DecisionRecord:
        self._report_change(report_id, change_id)
        row = self.session.get(Decision, (self.context.tenant_id, report_id, change_id))
        if row is None:
            return DecisionRecord(ReviewStatus.UNREVIEWED.value, 0, None, None)
        return DecisionRecord(row.status, row.version, row.updated_at, row.updated_by)

    def get_note(self, report_id: UUID, change_id: UUID) -> NoteRecord:
        self._report_change(report_id, change_id)
        row = self.session.get(ChangeNote, (self.context.tenant_id, report_id, change_id))
        if row is None:
            return NoteRecord("", 0, None, None)
        return NoteRecord(row.text, row.version, row.updated_at, row.updated_by)

    def set_decision(
        self,
        *,
        report_id: UUID,
        change_id: UUID,
        status: str,
        expected_version: int,
        idempotency_key: UUID,
        action: str | None = None,
    ) -> DecisionMutation:
        if action is not None:
            status = next_decision_status(self.get_decision(report_id, change_id).status, action)
        ReviewStatus(status)
        payload = {
            "status": status,
            "expected_version": expected_version,
            "report_id": str(report_id),
            "change_id": str(change_id),
        }
        digest = request_digest(payload)
        route = f"decision:{report_id}:{change_id}"
        replayed = self._idempotency(route, idempotency_key, digest)
        if replayed is not None:
            current = self.get_decision(report_id, change_id)
            return DecisionMutation(current, _as_int(replayed["last_sequence"]), replayed=True)
        review = self._review_for_report(report_id)
        self._authorize_review_write(review.repository_id)
        current = self.get_decision(report_id, change_id)
        if expected_version != current.version:
            raise VersionConflict(current)
        if current.status == status:
            self._store_idempotency(
                route,
                idempotency_key,
                digest,
                200,
                {"last_sequence": 0, "version": current.version},
            )
            return DecisionMutation(current, 0)
        now = utcnow()
        row = self.session.get(Decision, (self.context.tenant_id, report_id, change_id))
        if row is None:
            row = Decision(
                tenant_id=self.context.tenant_id,
                report_id=report_id,
                change_id=change_id,
                review_id=review.id,
                status=status,
                version=1,
                updated_by=self.context.actor_id,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.status = status
            row.version += 1
            row.updated_by = self.context.actor_id
            row.updated_at = now
        self.session.flush()
        sequence = self._append_history(
            kind="decision",
            review_id=review.id,
            report_id=report_id,
            change_id=change_id,
            before={"status": current.status, "version": current.version},
            after={"status": row.status, "version": row.version},
            resource_version=row.version,
            event_type="decision.updated",
        )
        result = DecisionRecord(row.status, row.version, row.updated_at, row.updated_by)
        self._store_idempotency(
            route,
            idempotency_key,
            digest,
            200,
            {"last_sequence": sequence, "version": row.version},
        )
        return DecisionMutation(result, sequence)

    def save_note(
        self,
        *,
        report_id: UUID,
        change_id: UUID,
        text: str,
        expected_version: int,
        idempotency_key: UUID,
    ) -> NoteMutation:
        if len(text) > NOTE_MAX_CHARS or len(text.encode("utf-8")) > NOTE_MAX_BYTES:
            raise WorkspaceError("note exceeds size limits")
        payload = {
            "text": text,
            "expected_version": expected_version,
            "report_id": str(report_id),
            "change_id": str(change_id),
        }
        digest = request_digest(payload)
        route = f"note:{report_id}:{change_id}"
        replayed = self._idempotency(route, idempotency_key, digest)
        if replayed is not None:
            current = self.get_note(report_id, change_id)
            return NoteMutation(current, _as_int(replayed["last_sequence"]), replayed=True)
        review = self._review_for_report(report_id)
        self._authorize_review_write(review.repository_id)
        current = self.get_note(report_id, change_id)
        if expected_version != current.version:
            raise VersionConflict(current)
        if current.text == text:
            self._store_idempotency(
                route,
                idempotency_key,
                digest,
                200,
                {"last_sequence": 0, "version": current.version},
            )
            return NoteMutation(current, 0)
        now = utcnow()
        row = self.session.get(ChangeNote, (self.context.tenant_id, report_id, change_id))
        if row is None:
            row = ChangeNote(
                tenant_id=self.context.tenant_id,
                report_id=report_id,
                change_id=change_id,
                review_id=review.id,
                text=text,
                version=1,
                updated_by=self.context.actor_id,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.text = text
            row.version += 1
            row.updated_by = self.context.actor_id
            row.updated_at = now
        self.session.flush()
        sequence = self._append_history(
            kind="note",
            review_id=review.id,
            report_id=report_id,
            change_id=change_id,
            before={"text": current.text, "version": current.version},
            after={"text": row.text, "version": row.version},
            resource_version=row.version,
            event_type="note.updated",
        )
        result = NoteRecord(row.text, row.version, row.updated_at, row.updated_by)
        self._store_idempotency(
            route,
            idempotency_key,
            digest,
            200,
            {"last_sequence": sequence, "version": row.version},
        )
        return NoteMutation(result, sequence)

    def progress(self, report_id: UUID) -> ProgressRecord:
        changes = self.session.scalars(
            select(ReportChange).where(
                ReportChange.tenant_id == self.context.tenant_id,
                ReportChange.report_id == report_id,
            )
        ).all()
        if not changes and self.session.get(Report, (self.context.tenant_id, report_id)) is None:
            raise NotFound("report not found")
        counts = {
            ReviewStatus.REVIEWED.value: 0,
            ReviewStatus.QUESTION.value: 0,
            ReviewStatus.BLOCKER.value: 0,
            ReviewStatus.UNREVIEWED.value: 0,
        }
        for change in changes:
            decision = self.session.get(
                Decision, (self.context.tenant_id, report_id, change.change_id)
            )
            status = decision.status if decision is not None else ReviewStatus.UNREVIEWED.value
            counts[status] += 1
        return ProgressRecord(
            reviewed=counts[ReviewStatus.REVIEWED.value],
            question=counts[ReviewStatus.QUESTION.value],
            blocker=counts[ReviewStatus.BLOCKER.value],
            unreviewed=counts[ReviewStatus.UNREVIEWED.value],
            total=len(changes),
            report_id=report_id,
        )

    def get_report(self, report_id: UUID) -> Report:
        report = self.session.get(Report, (self.context.tenant_id, report_id))
        if report is None:
            raise NotFound("report not found")
        return report

    def add_report(
        self,
        *,
        review_id: UUID,
        snapshot_id: UUID,
        kind: str,
        content_digest: str,
        config_digest: str,
        changes: list[tuple[UUID, str, int]],
        scope_summary: dict[str, object] | None = None,
        provenance: dict[str, object] | None = None,
        make_latest: bool = True,
    ) -> Report:
        review = self.session.get(Review, (self.context.tenant_id, review_id))
        if review is None:
            raise NotFound("review not found")
        self._authorize_review_write(review.repository_id)
        report = Report(
            tenant_id=self.context.tenant_id,
            id=uuid4(),
            review_id=review_id,
            snapshot_id=snapshot_id,
            kind=kind,
            schema_version=2,
            content_digest=content_digest,
            config_digest=config_digest,
            scope_summary=scope_summary or {},
            provenance=provenance or {},
        )
        self.session.add(report)
        for change_id, local_id, rank in changes:
            if (
                self.session.get(LogicalChange, (self.context.tenant_id, review_id, change_id))
                is None
            ):
                self.session.add(
                    LogicalChange(
                        tenant_id=self.context.tenant_id,
                        review_id=review_id,
                        id=change_id,
                        lineage={},
                    )
                )
            self.session.add(
                ReportChange(
                    tenant_id=self.context.tenant_id,
                    report_id=report.id,
                    change_id=change_id,
                    review_id=review_id,
                    local_id=local_id,
                    rank_index=rank,
                    projection={"noise": False},
                )
            )
        if make_latest:
            review.latest_report_id = report.id
            review.updated_at = utcnow()
        self.session.flush()
        return report

    def put_artifact(self, kind: str, payload: bytes) -> Artifact:
        self._membership()
        if self.artifact_root is None:
            raise WorkspaceError("artifact root is not configured")
        digest = write_tenant_bytes(self.artifact_root, self.context.tenant_id, payload)
        artifact = self.session.get(Artifact, (self.context.tenant_id, digest))
        if artifact is None:
            artifact = Artifact(
                tenant_id=self.context.tenant_id,
                digest=digest,
                kind=kind,
                byte_size=len(payload),
                storage_key=f"{self.context.tenant_id}/{digest}",
            )
            self.session.add(artifact)
            self.session.flush()
        return artifact

    def get_artifact_bytes(self, digest: str) -> bytes:
        self._membership()
        if self.artifact_root is None:
            raise WorkspaceError("artifact root is not configured")
        artifact = self.session.get(Artifact, (self.context.tenant_id, digest))
        if artifact is None:
            raise NotFound("artifact not found")
        return read_tenant_bytes(self.artifact_root, self.context.tenant_id, digest)

    def put_job(self, *, kind: str, status: str, phase: str, dedupe_key: str) -> Job:
        self._membership()
        job = Job(
            tenant_id=self.context.tenant_id,
            id=uuid4(),
            kind=kind,
            actor_id=self.context.actor_id,
            status=status,
            phase=phase,
            request_payload={},
            dedupe_key=dedupe_key,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def get_job(self, job_id: UUID) -> Job:
        job = self.session.get(Job, (self.context.tenant_id, job_id))
        if job is None:
            raise NotFound("job not found")
        return job

    def put_credential(self, *, kind: str, ciphertext: str, nonce: str, key_id: str) -> Credential:
        self._membership()
        credential = Credential(
            tenant_id=self.context.tenant_id,
            id=uuid4(),
            kind=kind,
            owner_user_id=self.context.actor_id if kind == "github" else None,
            provider_host="github.com",
            ciphertext=ciphertext,
            nonce=nonce,
            key_id=key_id,
            state="active",
        )
        self.session.add(credential)
        self.session.flush()
        return credential

    def get_credential(self, credential_id: UUID) -> Credential:
        credential = self.session.get(Credential, (self.context.tenant_id, credential_id))
        if credential is None:
            raise NotFound("credential not found")
        return credential

    def put_inbox_row(self, *, tab: str, repository_id: UUID, pr_number: int, title: str) -> None:
        self._membership()
        self.session.merge(
            InboxCache(
                tenant_id=self.context.tenant_id,
                user_id=self.context.actor_id,
                tab=tab,
                repository_id=repository_id,
                pr_number=pr_number,
                payload={"title": title},
                credential_version=1,
                fetched_at=utcnow(),
            )
        )
        self.session.flush()

    def list_inbox(self, tab: str) -> list[InboxCache]:
        self._membership()
        return list(
            self.session.scalars(
                select(InboxCache).where(
                    InboxCache.tenant_id == self.context.tenant_id,
                    InboxCache.user_id == self.context.actor_id,
                    InboxCache.tab == tab,
                )
            )
        )

    def events_after(self, sequence: int) -> list[Event]:
        self._membership()
        return list(
            self.session.scalars(
                select(Event)
                .where(
                    Event.tenant_id == self.context.tenant_id,
                    Event.sequence > sequence,
                )
                .order_by(Event.sequence)
            )
        )

    def review_event_count(self, report_id: UUID, change_id: UUID, kind: str) -> int:
        return len(
            self.session.scalars(
                select(ReviewEvent).where(
                    ReviewEvent.tenant_id == self.context.tenant_id,
                    ReviewEvent.report_id == report_id,
                    ReviewEvent.change_id == change_id,
                    ReviewEvent.kind == kind,
                )
            ).all()
        )

    def change_ids_for(self, report_id: UUID) -> dict[str, UUID]:
        rows = self.session.scalars(
            select(ReportChange).where(
                ReportChange.tenant_id == self.context.tenant_id,
                ReportChange.report_id == report_id,
            )
        )
        return {row.local_id: row.change_id for row in rows}

    def latest_report_id(self, review_id: UUID) -> UUID | None:
        review = self.session.get(Review, (self.context.tenant_id, review_id))
        if review is None:
            raise NotFound("review not found")
        return review.latest_report_id

    def save_personal_session(
        self,
        review_id: UUID,
        *,
        client_kind: str,
        selection: dict[str, object],
        history: list[object],
        report_id: UUID | None = None,
    ) -> PersonalSession:
        self._membership()
        review = self.session.get(Review, (self.context.tenant_id, review_id))
        if review is None:
            raise NotFound("review not found")
        now = utcnow()
        row = self.session.get(
            PersonalSession,
            (self.context.tenant_id, self.context.actor_id, review_id, client_kind),
        )
        if row is None:
            row = PersonalSession(
                tenant_id=self.context.tenant_id,
                user_id=self.context.actor_id,
                review_id=review_id,
                client_kind=client_kind,
                report_id=report_id or review.latest_report_id,
                selection=selection,
                history=history,
                version=1,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.selection = selection
            row.history = history
            row.report_id = report_id or row.report_id or review.latest_report_id
            row.version += 1
            row.updated_at = now
        self.session.flush()
        return row

    def get_personal_session(self, review_id: UUID, client_kind: str) -> PersonalSession | None:
        self._membership()
        return self.session.get(
            PersonalSession,
            (self.context.tenant_id, self.context.actor_id, review_id, client_kind),
        )


def create_local_graph(
    session: Session,
    *,
    slug: str,
    actor_name: str = "Local reviewer",
    target_key: str = "github:1:482",
    change_id: UUID | None = None,
) -> tuple[ActorContext, UUID, UUID, UUID]:
    tenant_id = uuid4()
    actor_id = uuid4()
    repository_id = uuid4()
    review_id = uuid4()
    snapshot_id = uuid4()
    selected = change_id or uuid4()
    session.add(
        Tenant(
            id=tenant_id,
            slug=slug,
            name=slug,
            state="active",
            authorization_version=1,
            limits={},
        )
    )
    session.add(
        User(
            id=actor_id,
            issuer="local",
            subject=slug,
            display_name=actor_name,
        )
    )
    session.flush()
    session.add(
        Membership(
            tenant_id=tenant_id,
            user_id=actor_id,
            role="administrator",
            state="active",
            version=1,
        )
    )
    session.add(
        Repository(
            tenant_id=tenant_id,
            id=repository_id,
            provider="github",
            host="github.com",
            provider_repository_id=str(abs(hash(slug)) % 10_000_000),
            display_name="acme/payments",
            state="active",
        )
    )
    session.flush()
    session.add(
        RepositoryGrant(
            tenant_id=tenant_id,
            repository_id=repository_id,
            user_id=actor_id,
            permission="review",
            version=1,
        )
    )
    session.add(
        Review(
            tenant_id=tenant_id,
            id=review_id,
            repository_id=repository_id,
            target_kind="github_pr",
            target_key=target_key,
            pr_number=482,
        )
    )
    session.flush()
    session.add(
        Snapshot(
            tenant_id=tenant_id,
            id=snapshot_id,
            review_id=review_id,
            head_sha="a" * 40,
            intent_digest="b" * 64,
            manifest_digest="c" * 64,
            diff_digest="d" * 64,
            acquisition_status="complete",
        )
    )
    session.flush()
    context = ActorContext(
        tenant_id=tenant_id,
        actor_id=actor_id,
        role="administrator",
        correlation_id=uuid4(),
        authorization_version=1,
    )
    workspace = TenantWorkspace(session, context)
    report = workspace.add_report(
        review_id=review_id,
        snapshot_id=snapshot_id,
        kind="static",
        content_digest="e" * 64,
        config_digest="f" * 64,
        changes=[(selected, "C1", 0)],
    )
    return context, review_id, report.id, selected
