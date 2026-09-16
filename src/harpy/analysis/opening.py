"""Tenant-aware opening, inbox refresh, and captured-source queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from harpy.analysis.capture import (
    CaptureError,
    CaptureLimits,
    GithubSource,
    InventoryLimit,
    capture_github,
    capture_local_repo,
    publish_static,
)
from harpy.config import HarpyConfig
from harpy.git.diff import parse_unified_diff
from harpy.git.local import (
    LocalSpec,
    RepositoryChanged,
    UnsupportedComparison,
    git_common_dir,
)
from harpy.identity.access import allows
from harpy.storage.schema import InboxCache, Job, SnapshotFile, utcnow
from harpy.storage.workspace import (
    AccessDenied,
    ActorContext,
    NotFound,
    TenantWorkspace,
    request_digest,
)

SOURCE_PAGE = 200
SOURCE_MAX = 1000
SOURCE_BYTES = 1_048_576


@dataclass(frozen=True)
class OpenSpec:
    repository_id: UUID
    kind: str
    acquire_latest: bool = False
    pr_number: int | None = None
    base_ref: str | None = None
    include_untracked: bool | None = None


@dataclass(frozen=True)
class OpenReady:
    state: Literal["ready"] = "ready"
    review_id: UUID = field(default_factory=uuid4)
    report_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class OpenQueued:
    state: Literal["queued"] = "queued"
    review_id: UUID = field(default_factory=uuid4)
    job_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class InboxRow:
    repository_id: UUID
    pr_number: int
    title: str
    author: str
    login: str


@dataclass(frozen=True)
class InboxView:
    tab: str
    rows: list[InboxRow]
    login: str | None
    error: str | None
    fetched_at: datetime | None
    truncated: bool
    job_id: UUID | None = None
    clone_calls: int = 0
    semantic_calls: int = 0


@dataclass(frozen=True)
class DiffRow:
    row_id: str
    kind: Literal["context", "addition", "deletion"]
    base_line: int | None
    head_line: int | None
    text: str
    hunk_id: str | None
    owner_change_ids: list[UUID]


@dataclass(frozen=True)
class DiffView:
    report_id: UUID
    file_id: UUID
    mode: str
    rows: list[DiffRow]
    limitations: list[str]
    patch: str | None = None


@dataclass(frozen=True)
class SourceLine:
    number: int
    text: str
    continuation: bool = False


@dataclass(frozen=True)
class SourceView:
    snapshot_id: UUID
    file_id: UUID
    side: str
    blob_digest: str | None
    available: bool
    reason: str | None
    start_line: int
    lines: list[SourceLine]
    host_path: None = None


@dataclass(frozen=True)
class ChangeView:
    change_id: UUID
    local_id: str
    title: str
    rank_index: int
    importance: float
    unexpectedness: float
    confidence: float
    risk: str
    file_count: int
    hunk_count: int
    noise: bool
    status: str
    paths: list[str]
    hunk_ids: list[str]


@dataclass(frozen=True)
class ReportView:
    report_id: UUID
    review_id: UUID
    snapshot_id: UUID
    kind: str
    created_at: datetime
    analyzed_revision: str | None
    freshness: str
    change_count: int
    hunk_count: int
    limitations: list[str]


class MissingGithubCredential(RuntimeError):
    def __init__(self) -> None:
        super().__init__("missing_github_credential")


class TenantReviewService:
    def __init__(
        self,
        session: Session,
        context: ActorContext,
        *,
        artifact_root: Path,
        config: HarpyConfig,
        github: GithubSource | None = None,
        limits: CaptureLimits | None = None,
    ) -> None:
        self.session = session
        self.context = context
        self.workspace = TenantWorkspace(session, context, artifact_root=artifact_root)
        self.config = config
        self.github = github
        self.limits = limits or CaptureLimits()
        self.semantic_calls = 0

    def register_local_repository(self, root: Path) -> UUID:
        resolved = root.resolve()
        if not resolved.is_dir():
            raise AccessDenied("local repository not found")
        common = git_common_dir(resolved)
        ref = f"{resolved}|{common}"
        repository = self.workspace.add_repository(
            provider="local",
            host="local",
            display_name=resolved.name,
            local_registration_ref=ref,
        )
        return repository.id

    def local_root(self, repository_id: UUID) -> Path:
        repository = self.workspace.get_repository(repository_id)
        if repository.provider != "local" or not repository.local_registration_ref:
            raise NotFound("not found")
        path = Path(repository.local_registration_ref.split("|", 1)[0])
        if not path.is_dir():
            raise CaptureError("registered repository is missing")
        return path

    def open_target(self, spec: OpenSpec, *, idempotency_key: UUID) -> OpenReady | OpenQueued:
        payload = {
            "repository_id": str(spec.repository_id),
            "kind": spec.kind,
            "acquire_latest": spec.acquire_latest,
            "pr_number": spec.pr_number,
            "base_ref": spec.base_ref,
            "include_untracked": spec.include_untracked,
        }
        digest = request_digest(payload)
        route = f"reviews.open:{spec.repository_id}"
        replayed = self.workspace.replay(route, idempotency_key, digest)
        if replayed is not None:
            return _open_from_payload(replayed)
        repository = self.workspace.get_repository(spec.repository_id)
        target_key, local_spec = _target_key(spec, repository.provider_repository_id)
        review = (
            self.workspace.find_review_pr(spec.repository_id, spec.pr_number)
            if spec.kind == "github_pr" and spec.pr_number is not None
            else self.workspace.find_review(spec.repository_id, target_key)
        )
        if review is not None and review.latest_report_id and not spec.acquire_latest:
            ready = OpenReady(review_id=review.id, report_id=review.latest_report_id)
            self.workspace.remember(route, idempotency_key, digest, _open_payload(ready))
            return ready
        grant = self.workspace.authorize_read(spec.repository_id)
        if not allows(role=self.context.role, grant=grant.permission, action="acquire"):
            raise AccessDenied("role cannot acquire")
        review = self.workspace.get_or_create_review(
            repository_id=spec.repository_id,
            target_kind=spec.kind,
            target_key=target_key,
            pr_number=spec.pr_number,
            local_spec=local_spec,
        )
        dedupe = f"acquire:{spec.repository_id}:{target_key}"
        job = self.workspace.enqueue_job(
            kind="acquire",
            dedupe_key=dedupe,
            review_id=review.id,
            request_payload=payload,
        )
        queued = OpenQueued(review_id=review.id, job_id=job.id)
        self.workspace.remember(route, idempotency_key, digest, _open_payload(queued), status=202)
        return queued

    def inbox(self, tab: str, *, open_only: bool = True, idempotency_key: UUID) -> InboxView:
        entries, meta = self.workspace.inbox_rows(tab)
        if meta is None and not entries:
            job = self.refresh_inbox(tab, open_only=open_only, idempotency_key=idempotency_key)
            return InboxView(
                tab=tab,
                rows=[],
                login=None,
                error=None,
                fetched_at=None,
                truncated=False,
                job_id=job,
                clone_calls=self.github.clone_calls if self.github else 0,
                semantic_calls=self.semantic_calls,
            )
        return self._inbox_view(tab, entries, meta)

    def refresh_inbox(self, tab: str, *, open_only: bool = True, idempotency_key: UUID) -> UUID:
        payload = {"tab": tab, "open_only": open_only}
        digest = request_digest(payload)
        route = f"inbox.refresh:{tab}"
        replayed = self.workspace.replay(route, idempotency_key, digest)
        if replayed is not None:
            return UUID(str(replayed["job_id"]))
        job = self.workspace.enqueue_job(
            kind="refresh",
            dedupe_key=f"refresh:{self.context.actor_id}:{tab}:{open_only}",
            request_payload=payload,
        )
        self.workspace.remember(route, idempotency_key, digest, {"job_id": str(job.id)}, status=202)
        return job.id

    def list_inbox(self, tab: str) -> InboxView:
        entries, meta = self.workspace.inbox_rows(tab)
        return self._inbox_view(tab, entries, meta)

    def run_job(self, job_id: UUID) -> Job:
        job = self.workspace.get_job(job_id)
        if job.status not in {"queued", "running"}:
            return job
        self.workspace.mark_job(job, status="running", phase="resolving_target")
        try:
            if job.kind == "refresh":
                self._run_refresh(job)
            elif job.kind == "acquire":
                self._run_acquire(job)
            else:
                raise CaptureError("unsupported job")
        except MissingGithubCredential:
            self.workspace.mark_job(
                job,
                status="failed",
                phase="finished",
                error={
                    "code": "missing_github_credential",
                    "message": "GitHub credential required",
                },
            )
        except RepositoryChanged as exc:
            self.workspace.mark_job(
                job,
                status="failed",
                phase="finished",
                error={"code": "repository_changed", "message": str(exc)},
            )
        except UnsupportedComparison as exc:
            self.workspace.mark_job(
                job,
                status="failed",
                phase="finished",
                error={"code": "unsupported_comparison", "message": str(exc)},
            )
        except InventoryLimit as exc:
            self.workspace.mark_job(
                job,
                status="failed",
                phase="finished",
                error={"code": "inventory_limit", "message": str(exc)},
            )
        except CaptureError as exc:
            self.workspace.mark_job(
                job,
                status="failed",
                phase="finished",
                error={"code": "capture_failed", "message": str(exc)},
            )
        return self.workspace.get_job(job_id)

    def get_report(self, review_id: UUID, report_id: UUID) -> ReportView:
        review = self.workspace.get_review(review_id)
        report = self.workspace.get_report(report_id)
        if report.review_id != review_id:
            raise NotFound("report not found")
        snapshot = self.workspace.get_snapshot(report.snapshot_id)
        changes = self.workspace.report_changes(report_id)
        hunks = sum(len(_as_list(item.projection.get("hunk_ids"))) for item in changes)
        return ReportView(
            report_id=report.id,
            review_id=review.id,
            snapshot_id=report.snapshot_id,
            kind=report.kind,
            created_at=report.created_at,
            analyzed_revision=snapshot.head_sha or snapshot.local_digest,
            freshness=_freshness(snapshot, review.last_observation),
            change_count=len(changes),
            hunk_count=hunks,
            limitations=_limitations(self.workspace.snapshot_files(snapshot.id)),
        )

    def list_changes(self, report_id: UUID) -> list[ChangeView]:
        report = self.workspace.get_report(report_id)
        self.workspace.get_review(report.review_id)
        views: list[ChangeView] = []
        for row in self.workspace.report_changes(report_id):
            decision = self.workspace.get_decision(report_id, row.change_id)
            projection = row.projection
            views.append(
                ChangeView(
                    change_id=row.change_id,
                    local_id=row.local_id,
                    title=str(projection.get("title") or row.local_id),
                    rank_index=row.rank_index,
                    importance=_as_float(projection.get("importance")),
                    unexpectedness=_as_float(projection.get("unexpectedness")),
                    confidence=_as_float(projection.get("confidence")),
                    risk=str(projection.get("risk") or "low"),
                    file_count=_as_int(projection.get("file_count")),
                    hunk_count=_as_int(projection.get("hunk_count")),
                    noise=bool(projection.get("noise")),
                    status=decision.status,
                    paths=_as_str_list(projection.get("paths")),
                    hunk_ids=_as_str_list(projection.get("hunk_ids")),
                )
            )
        return views

    def get_diff(self, report_id: UUID, file_id: UUID, *, mode: str = "focused") -> DiffView:
        report = self.workspace.get_report(report_id)
        snapshot = self.workspace.get_snapshot(report.snapshot_id)
        stored = self.workspace.snapshot_file(snapshot.id, file_id)
        patch = self.workspace.get_artifact_bytes(snapshot.diff_digest).decode("utf-8")
        owners = _hunk_owners(self.list_changes(report_id), stored.path)
        rows = _diff_rows(patch, stored.path, file_id, owners)
        limitations = [stored.availability_reason] if stored.availability_reason else []
        return DiffView(
            report_id=report_id,
            file_id=file_id,
            mode=mode,
            rows=rows if mode != "patch" else _patch_rows(patch, file_id, stored.path),
            limitations=limitations,
            patch=patch,
        )

    def get_source(
        self,
        report_id: UUID,
        file_id: UUID,
        *,
        side: str,
        start_line: int = 1,
        limit: int = SOURCE_PAGE,
    ) -> SourceView:
        report = self.workspace.get_report(report_id)
        snapshot = self.workspace.get_snapshot(report.snapshot_id)
        stored = self.workspace.snapshot_file(snapshot.id, file_id)
        digest = stored.head_artifact if side == "head" else stored.base_artifact
        available = stored.head_available if side == "head" else stored.base_available
        reason = None if available else stored.availability_reason or "absent_side"
        if side == "base" and stored.kind == "file" and not stored.base_available:
            reason = stored.availability_reason or "absent_side"
        lines: list[SourceLine] = []
        if available and digest:
            text = self.workspace.get_artifact_bytes(digest).decode("utf-8")
            raw = text.splitlines()
            capped = min(max(limit, 1), SOURCE_MAX)
            start = max(start_line, 1)
            chunk = raw[start - 1 : start - 1 + capped]
            used = 0
            for offset, line in enumerate(chunk):
                used += len(line.encode("utf-8"))
                if used > SOURCE_BYTES:
                    break
                lines.append(SourceLine(number=start + offset, text=line))
        return SourceView(
            snapshot_id=snapshot.id,
            file_id=file_id,
            side=side,
            blob_digest=digest,
            available=available,
            reason=reason,
            start_line=max(start_line, 1),
            lines=lines,
        )

    def snapshot_files(self, report_id: UUID) -> list[SnapshotFile]:
        report = self.workspace.get_report(report_id)
        return self.workspace.snapshot_files(report.snapshot_id)

    def _inbox_view(
        self, tab: str, entries: list[InboxCache], meta: InboxCache | None
    ) -> InboxView:
        credential = self.workspace.github_credential()
        login = credential.verified_login if credential is not None else None
        rows = [
            InboxRow(
                repository_id=row.repository_id,
                pr_number=row.pr_number,
                title=str(row.payload.get("title") or ""),
                author=str(row.payload.get("author") or ""),
                login=str(row.payload.get("login") or login or ""),
            )
            for row in entries
        ]
        return InboxView(
            tab=tab,
            rows=rows,
            login=login,
            error=meta.error if meta is not None else None,
            fetched_at=meta.fetched_at if meta is not None else None,
            truncated=bool((meta.payload if meta is not None else {}).get("truncated")),
            clone_calls=self.github.clone_calls if self.github else 0,
            semantic_calls=self.semantic_calls,
        )

    def _run_refresh(self, job: Job) -> None:
        tab = str(job.request_payload.get("tab") or "")
        open_only = bool(job.request_payload.get("open_only", True))
        credential = self.workspace.github_credential()
        if credential is None or self.github is None:
            entries, meta = self.workspace.inbox_rows(tab)
            self.workspace.replace_inbox(
                tab=tab,
                rows=_inbox_payloads(entries),
                credential_version=credential.version if credential else 0,
                error="missing_github_credential",
                truncated=bool((meta.payload if meta else {}).get("truncated")),
                fetched_at=meta.fetched_at if meta is not None else utcnow(),
            )
            raise MissingGithubCredential()
        try:
            page = self.github.search_prs(
                tab, open_only=open_only, login=credential.verified_login or ""
            )
        except Exception as exc:
            entries, meta = self.workspace.inbox_rows(tab)
            self.workspace.replace_inbox(
                tab=tab,
                rows=_inbox_payloads(entries),
                credential_version=credential.version,
                error=str(exc),
                truncated=bool((meta.payload if meta else {}).get("truncated")),
                fetched_at=meta.fetched_at if meta is not None else None,
            )
            self.workspace.mark_job(
                job, status="failed", phase="finished", error={"code": "inbox_refresh_failed"}
            )
            return
        rows = [
            {
                "repository_id": str(item.repository_id or uuid4()),
                "pr_number": item.number,
                "title": item.title,
                "author": item.author,
                "login": self.github.login,
            }
            for item in page.rows
        ]
        self.workspace.replace_inbox(
            tab=tab,
            rows=rows,
            credential_version=credential.version,
            error=None,
            truncated=page.truncated,
        )
        self.workspace.mark_job(job, status="completed", phase="finished")

    def _run_acquire(self, job: Job) -> None:
        payload = job.request_payload
        spec = OpenSpec(
            repository_id=UUID(str(payload["repository_id"])),
            kind=str(payload["kind"]),
            acquire_latest=bool(payload.get("acquire_latest")),
            pr_number=_as_optional_int(payload.get("pr_number")),
            base_ref=str(payload["base_ref"]) if payload.get("base_ref") else None,
            include_untracked=_as_optional_bool(payload.get("include_untracked"))
            if "include_untracked" in payload
            else None,
        )
        repository = self.workspace.get_repository(spec.repository_id)
        review = self.workspace.get_review(job.review_id) if job.review_id else None
        if review is None:
            raise CaptureError("review missing")
        self.workspace.mark_job(job, status="running", phase="capturing")
        if spec.kind == "github_pr":
            if self.workspace.github_credential() is None or self.github is None:
                raise MissingGithubCredential()
            if spec.pr_number is None:
                raise CaptureError("pr_number required")
            bundle = capture_github(
                self.github,
                repo=repository.display_name,
                number=spec.pr_number,
                limits=self.limits,
            )
        else:
            root = self.local_root(spec.repository_id)
            local = LocalSpec(
                mode=_local_mode(spec.kind),
                base=spec.base_ref,
                include_untracked=bool(spec.include_untracked),
            )
            bundle = capture_local_repo(
                root, local, limits=self.limits, title=repository.display_name
            )
        self.workspace.mark_job(job, status="running", phase="static_analysis")
        report_id = publish_static(
            self.workspace, review_id=review.id, bundle=bundle, config=self.config
        )
        report = self.workspace.get_report(report_id)
        self.workspace.mark_job(
            job,
            status="completed",
            phase="finished",
            result_report_id=report_id,
            snapshot_id=report.snapshot_id,
        )


def _inbox_payloads(entries: list[InboxCache]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in entries:
        payload = dict(row.payload)
        payload["repository_id"] = str(row.repository_id)
        payload["pr_number"] = row.pr_number
        rows.append(payload)
    return rows


def _local_mode(kind: str) -> str:
    mapping = {
        "local_committed": "committed",
        "local_staged": "staged",
        "local_working_tree": "working-tree",
    }
    if kind not in mapping:
        raise CaptureError("unsupported comparison")
    return mapping[kind]


def _target_key(
    spec: OpenSpec, provider_repository_id: str | None
) -> tuple[str, dict[str, object] | None]:
    if spec.kind == "github_pr":
        return f"{provider_repository_id}:{spec.pr_number}", None
    payload = {
        "mode": spec.kind,
        "base_ref": spec.base_ref,
        "include_untracked": spec.include_untracked,
        "repository_id": str(spec.repository_id),
    }
    digest = sha256(dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    local_spec: dict[str, object] = dict(payload)
    return digest, local_spec


def _open_payload(result: OpenReady | OpenQueued) -> dict[str, object]:
    if result.state == "ready":
        return {
            "state": "ready",
            "review_id": str(result.review_id),
            "report_id": str(result.report_id),
        }
    return {"state": "queued", "review_id": str(result.review_id), "job_id": str(result.job_id)}


def _open_from_payload(payload: dict[str, object]) -> OpenReady | OpenQueued:
    if payload.get("state") == "ready":
        return OpenReady(
            review_id=UUID(str(payload["review_id"])), report_id=UUID(str(payload["report_id"]))
        )
    return OpenQueued(
        review_id=UUID(str(payload["review_id"])), job_id=UUID(str(payload["job_id"]))
    )


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return int(str(value or 0))
    return value


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return float(str(value or 0))
    return float(value)


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _as_int(value)


def _as_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item) for item in _as_list(value)]


def _freshness(snapshot: object, observation: dict[str, object] | None) -> str:
    if observation is None:
        return "unknown"
    head = getattr(snapshot, "head_sha", None)
    local = getattr(snapshot, "local_digest", None)
    intent = getattr(snapshot, "intent_digest", None)
    obs_head = observation.get("head_sha")
    obs_local = observation.get("local_digest")
    obs_intent = observation.get("intent_digest")
    if obs_head is None and obs_local is None:
        return "unknown"
    code_changed = (head and obs_head and head != obs_head) or (
        local and obs_local and local != obs_local
    )
    intent_changed = bool(intent and obs_intent and intent != obs_intent)
    if local and obs_local and local != obs_local and not head:
        return "local_changed" if not intent_changed else "code_and_intent_changed"
    if code_changed and intent_changed:
        return "code_and_intent_changed"
    if code_changed:
        return "code_changed"
    if intent_changed:
        return "intent_changed"
    return "current"


def _limitations(files: list[SnapshotFile]) -> list[str]:
    reasons = [row.availability_reason for row in files if row.availability_reason]
    return list(dict.fromkeys(reasons))


def _hunk_owners(changes: list[ChangeView], path: str) -> dict[str, list[UUID]]:
    owners: dict[str, list[UUID]] = {}
    for change in changes:
        if path not in change.paths and change.paths:
            continue
        for hunk_id in change.hunk_ids:
            owners.setdefault(hunk_id, []).append(change.change_id)
    return owners


def _diff_rows(
    patch: str, path: str, file_id: UUID, owners: dict[str, list[UUID]]
) -> list[DiffRow]:
    files = parse_unified_diff(patch)
    target = next((item for item in files if item.path == path), None)
    if target is None:
        return []
    rows: list[DiffRow] = []
    index = 0
    for hunk in target.hunks:
        old = hunk.old_start
        new = hunk.new_start
        claimed = owners.get(hunk.id, [])
        for line in hunk.patch.splitlines():
            if line.startswith("@@"):
                continue
            index += 1
            if line.startswith("+"):
                kind: Literal["context", "addition", "deletion"] = "addition"
                rows.append(
                    DiffRow(
                        f"{file_id}:{hunk.id}:{index}",
                        kind,
                        None,
                        new,
                        line[1:],
                        hunk.id,
                        claimed,
                    )
                )
                new += 1
            elif line.startswith("-"):
                rows.append(
                    DiffRow(
                        f"{file_id}:{hunk.id}:{index}",
                        "deletion",
                        old,
                        None,
                        line[1:],
                        hunk.id,
                        claimed,
                    )
                )
                old += 1
            else:
                text = line[1:] if line.startswith(" ") else line
                rows.append(
                    DiffRow(
                        f"{file_id}:{hunk.id}:{index}",
                        "context",
                        old,
                        new,
                        text,
                        hunk.id,
                        claimed,
                    )
                )
                old += 1
                new += 1
    return rows


def _patch_rows(patch: str, file_id: UUID, path: str) -> list[DiffRow]:
    rows: list[DiffRow] = []
    capture = False
    index = 0
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            capture = f" b/{path}" in line or line.endswith(f" b/{path}")
        if not capture:
            continue
        index += 1
        rows.append(DiffRow(f"{file_id}:patch:{index}", "context", None, None, line, None, []))
    return rows
