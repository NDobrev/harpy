"""Import unmigrated local JSON/catalog roots into tenant-aware SQL."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from harpy.models import AnalysisResult, ReviewStatus, ScopePreset
from harpy.prefs import PrefsStore
from harpy.review_scope import BUILTIN_PRESETS
from harpy.storage.backend import (
    BACKEND_SQL,
    DATABASE_NAME,
    MIN_APP_VERSION,
    SCHEMA_GENERATION,
    BackendIncompatibleError,
    BackendMarker,
    database_file,
    read_marker,
    write_marker,
)
from harpy.storage.engine import create_sqlite_engine, initialize_engine
from harpy.storage.schema import (
    Artifact,
    ChangeNote,
    Decision,
    LegacyHumanWork,
    LogicalChange,
    Membership,
    MigrationImport,
    PersonalSession,
    Preference,
    Preset,
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
from harpy.storage.tenant_files import write_tenant_bytes

LEGACY_ISSUER = "legacy-import"
LEGACY_SUBJECT = "legacy"
LEGACY_NAME = "Legacy import"
LOCAL_ISSUER = "local"
LOCAL_SUBJECT = "implicit"
LOCAL_SLUG = "local"
LOCK_NAME = "migration.lock"
EMPTY_DIGEST = sha256(b"").hexdigest()


class ImportError(RuntimeError):
    pass


class ImportRefused(ImportError):
    pass


@dataclass
class ImportResult:
    import_id: UUID
    tenant_id: UUID
    actor_id: UUID
    backup_dir: Path | None
    state: str
    counts: dict[str, object]
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False
    source_fingerprint: str = ""


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImportError(f"corrupt legacy file {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ImportError(f"corrupt legacy file {path}: expected object")
    return {str(key): value for key, value in loaded.items()}


def _as_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return default
    return value


def source_fingerprint(root: Path) -> str:
    digest = sha256()
    for name in ("browser.json", "review.json", "review.sqlite3"):
        path = root / name
        digest.update(name.encode("utf-8"))
        if path.is_file():
            digest.update(_sha256_file(path).encode("ascii"))
        else:
            digest.update(b"missing")
    for folder in ("results", "reports"):
        directory = root / folder
        digest.update(folder.encode("utf-8"))
        if not directory.is_dir():
            continue
        for path in sorted(item for item in directory.iterdir() if item.is_file()):
            digest.update(path.name.encode("utf-8"))
            digest.update(_sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _inspect_legacy(root: Path) -> dict[str, object]:
    review_path = root / "review.json"
    if review_path.is_file():
        data = _read_json(review_path)
        version = _as_int(data.get("schema_version"), 0)
        if version > 1:
            raise ImportRefused(
                f"legacy schema {version} in {review_path} is newer than application 1"
            )
    sqlite_path = root / "review.sqlite3"
    if sqlite_path.is_file():
        header = sqlite_path.read_bytes()[:16]
        if header and not header.startswith(b"SQLite format 3"):
            raise ImportError(f"corrupt legacy file {sqlite_path}: not a SQLite database")
    if (root / "browser.json").is_file():
        _read_json(root / "browser.json")
    return {"ok": True}


@contextmanager
def _migration_lock(root: Path) -> Iterator[None]:
    import fcntl

    root.mkdir(parents=True, exist_ok=True)
    handle = (root / LOCK_NAME).open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _copy_tree(source: Path, dest: Path, manifest: dict[str, str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        target = dest / source.name
        shutil.copy2(source, target)
        manifest[source.name] = _sha256_file(source)
        return
    for path in source.iterdir():
        rel = path.name
        target = dest / rel
        if path.is_dir():
            _copy_tree(path, target, manifest)
        elif path.is_file():
            shutil.copy2(path, target)
            manifest[str(Path(source.name) / rel) if source.name else rel] = _sha256_file(path)


def _backup_root(root: Path) -> Path:
    dest = root.parent / f"{root.name}.backup-{_now_stamp()}"
    dest.mkdir(parents=False)
    manifest: dict[str, str] = {}
    for name in ("browser.json", "review.json", "review.sqlite3", "results", "reports"):
        path = root / name
        if path.exists():
            _copy_tree(path, dest / name if path.is_dir() else dest, manifest)
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), "utf-8")
    return dest


def _parse_uuid(raw: object) -> UUID | None:
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _change_id(report_id: UUID, local_id: str) -> UUID:
    parsed = _parse_uuid(local_id)
    return parsed if parsed is not None else uuid5(report_id, local_id)


def _valid_status(raw: object) -> str | None:
    text = str(raw or "").strip().lower()
    try:
        return ReviewStatus(text).value
    except ValueError:
        return None


def _parse_time(raw: object) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ensure_identities(session: Session) -> tuple[UUID, UUID, UUID]:
    tenant = session.scalar(select(Tenant).where(Tenant.slug == LOCAL_SLUG))
    if tenant is None:
        tenant = Tenant(
            id=uuid4(),
            slug=LOCAL_SLUG,
            name="Local",
            state="active",
            authorization_version=1,
            limits={},
        )
        session.add(tenant)
        session.flush()
    actor = session.scalar(
        select(User).where(User.issuer == LOCAL_ISSUER, User.subject == LOCAL_SUBJECT)
    )
    if actor is None:
        actor = User(
            id=uuid4(),
            issuer=LOCAL_ISSUER,
            subject=LOCAL_SUBJECT,
            display_name="Local reviewer",
        )
        session.add(actor)
        session.flush()
    legacy = session.scalar(
        select(User).where(User.issuer == LEGACY_ISSUER, User.subject == LEGACY_SUBJECT)
    )
    if legacy is None:
        legacy = User(
            id=uuid4(),
            issuer=LEGACY_ISSUER,
            subject=LEGACY_SUBJECT,
            display_name=LEGACY_NAME,
        )
        session.add(legacy)
        session.flush()
    if session.get(Membership, (tenant.id, actor.id)) is None:
        session.add(
            Membership(
                tenant_id=tenant.id,
                user_id=actor.id,
                role="administrator",
                state="active",
                version=1,
            )
        )
        session.flush()
    return tenant.id, actor.id, legacy.id


def _repository(
    session: Session,
    tenant_id: UUID,
    actor_id: UUID,
    *,
    repo: str,
    source: str,
    title: str,
) -> UUID:
    provider = "github" if repo and source != "local" else "local"
    host = "github.com" if provider == "github" else "local"
    provider_id = repo or title or "local"
    existing = session.scalar(
        select(Repository).where(
            Repository.tenant_id == tenant_id,
            Repository.provider == provider,
            Repository.host == host,
            Repository.provider_repository_id == provider_id,
        )
    )
    if existing is not None:
        return existing.id
    repository_id = uuid4()
    session.add(
        Repository(
            tenant_id=tenant_id,
            id=repository_id,
            provider=provider,
            host=host,
            provider_repository_id=provider_id,
            display_name=repo or title or "local",
            state="active",
        )
    )
    session.flush()
    if session.get(RepositoryGrant, (tenant_id, repository_id, actor_id)) is None:
        session.add(
            RepositoryGrant(
                tenant_id=tenant_id,
                repository_id=repository_id,
                user_id=actor_id,
                permission="review",
                version=1,
            )
        )
        session.flush()
    return repository_id


def _attach_unattached(
    session: Session,
    *,
    tenant_id: UUID,
    import_id: UUID,
    review_ref: str,
    change_ref: str,
    kind: str,
    payload: dict[str, object],
    reason: str,
) -> None:
    session.add(
        LegacyHumanWork(
            tenant_id=tenant_id,
            id=uuid4(),
            import_id=import_id,
            original_review_ref=review_ref,
            original_change_ref=change_ref,
            kind=kind,
            payload=payload,
            reason=reason,
        )
    )


def _put_history(
    session: Session,
    *,
    tenant_id: UUID,
    review_id: UUID,
    report_id: UUID,
    change_id: UUID,
    actor_id: UUID,
    kind: str,
    before: dict[str, object],
    after: dict[str, object],
    version: int,
) -> None:
    session.add(
        ReviewEvent(
            tenant_id=tenant_id,
            id=uuid4(),
            review_id=review_id,
            report_id=report_id,
            change_id=change_id,
            actor_id=actor_id,
            kind=kind,
            before_state=before,
            after_state=after,
            resource_version=version,
            correlation_id=uuid4(),
        )
    )


def _set_decision(
    session: Session,
    *,
    tenant_id: UUID,
    review_id: UUID,
    report_id: UUID,
    change_id: UUID,
    actor_id: UUID,
    status: str,
) -> None:
    row = session.get(Decision, (tenant_id, report_id, change_id))
    if row is None:
        session.add(
            Decision(
                tenant_id=tenant_id,
                report_id=report_id,
                change_id=change_id,
                review_id=review_id,
                status=status,
                version=1,
                updated_by=actor_id,
            )
        )
        _put_history(
            session,
            tenant_id=tenant_id,
            review_id=review_id,
            report_id=report_id,
            change_id=change_id,
            actor_id=actor_id,
            kind="decision",
            before={"status": ReviewStatus.UNREVIEWED.value, "version": 0},
            after={"status": status, "version": 1},
            version=1,
        )
        return
    if row.status == status:
        return
    before = {"status": row.status, "version": row.version}
    row.status = status
    row.version += 1
    row.updated_by = actor_id
    row.updated_at = utcnow()
    _put_history(
        session,
        tenant_id=tenant_id,
        review_id=review_id,
        report_id=report_id,
        change_id=change_id,
        actor_id=actor_id,
        kind="decision",
        before=before,
        after={"status": row.status, "version": row.version},
        version=row.version,
    )


def _set_note(
    session: Session,
    *,
    tenant_id: UUID,
    review_id: UUID,
    report_id: UUID,
    change_id: UUID,
    actor_id: UUID,
    text: str,
) -> None:
    row = session.get(ChangeNote, (tenant_id, report_id, change_id))
    if row is None:
        session.add(
            ChangeNote(
                tenant_id=tenant_id,
                report_id=report_id,
                change_id=change_id,
                review_id=review_id,
                text=text,
                version=1,
                updated_by=actor_id,
            )
        )
        _put_history(
            session,
            tenant_id=tenant_id,
            review_id=review_id,
            report_id=report_id,
            change_id=change_id,
            actor_id=actor_id,
            kind="note",
            before={"text": "", "version": 0},
            after={"text": text, "version": 1},
            version=1,
        )
        return
    if row.text == text:
        return
    before = {"text": row.text, "version": row.version}
    row.text = text
    row.version += 1
    row.updated_by = actor_id
    row.updated_at = utcnow()
    _put_history(
        session,
        tenant_id=tenant_id,
        review_id=review_id,
        report_id=report_id,
        change_id=change_id,
        actor_id=actor_id,
        kind="note",
        before=before,
        after={"text": row.text, "version": row.version},
        version=row.version,
    )


def _load_result(root: Path, digest: str) -> tuple[AnalysisResult | None, bytes | None]:
    path = root / "results" / digest
    if not path.is_file():
        return None, None
    payload = path.read_bytes()
    try:
        return AnalysisResult.model_validate_json(payload), payload
    except Exception:
        return None, payload


def _import_catalog(
    session: Session,
    root: Path,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    legacy_id: UUID,
    import_id: UUID,
    warnings: list[str],
) -> dict[UUID, UUID]:
    review_reports: dict[UUID, UUID] = {}
    catalog_path = root / "browser.json"
    if not catalog_path.is_file():
        return review_reports
    data = _read_json(catalog_path)
    entries = _as_map(data.get("entries"))
    artifact_root = root / "artifacts"
    for raw in entries.values():
        if not isinstance(raw, dict):
            continue
        review_id = _parse_uuid(raw.get("review_id"))
        if review_id is None:
            warnings.append("catalog entry missing review_id")
            continue
        report_id = _parse_uuid(raw.get("report_id")) or uuid4()
        repo = str(raw.get("repo") or "")
        title = str(raw.get("title") or "")
        source = str(raw.get("source") or "github")
        number = raw.get("number")
        pr_number = number if isinstance(number, int) else None
        repository_id = _repository(
            session, tenant_id, actor_id, repo=repo, source=source, title=title
        )
        target_kind = "github_pr" if pr_number is not None and repo else "local_committed"
        target_key = (
            f"github:{repo}:{pr_number}" if target_kind == "github_pr" else f"local:{review_id}"
        )
        if session.get(Review, (tenant_id, review_id)) is None:
            session.add(
                Review(
                    tenant_id=tenant_id,
                    id=review_id,
                    repository_id=repository_id,
                    target_kind=target_kind,
                    target_key=target_key,
                    pr_number=pr_number,
                )
            )
            session.flush()
        digest = str(raw.get("result_file") or "")
        result, payload = _load_result(root, digest) if digest else (None, None)
        report_row = session.get(Report, (tenant_id, report_id))
        if report_row is not None:
            review_reports[review_id] = report_id
            continue
        snapshot_id = uuid4()
        analyzed = str(raw.get("analyzed_rev") or "")
        head_sha = analyzed if len(analyzed) >= 7 else None
        session.add(
            Snapshot(
                tenant_id=tenant_id,
                id=snapshot_id,
                review_id=review_id,
                head_sha=head_sha,
                intent_digest=_sha256_bytes(f"intent:{review_id}".encode()),
                manifest_digest=_sha256_bytes(f"manifest:{review_id}".encode()),
                diff_digest=_sha256_bytes(f"diff:{review_id}".encode()),
                acquisition_status="legacy",
            )
        )
        session.flush()
        changes: list[tuple[UUID, str, int]] = []
        if result is not None:
            for index, change in enumerate(result.changes):
                local_id = change.id
                change_id = _change_id(report_id, local_id)
                if session.get(LogicalChange, (tenant_id, review_id, change_id)) is None:
                    session.add(
                        LogicalChange(
                            tenant_id=tenant_id,
                            review_id=review_id,
                            id=change_id,
                            lineage={"local_id": local_id},
                        )
                    )
                changes.append((change_id, local_id, index))
            session.flush()
        content = _sha256_bytes(payload or str(report_id).encode())
        if payload is not None:
            write_tenant_bytes(artifact_root, tenant_id, payload)
            session.merge(
                Artifact(
                    tenant_id=tenant_id,
                    digest=content,
                    kind="legacy-result",
                    byte_size=len(payload),
                    storage_key=f"{tenant_id}/{content}",
                )
            )
        session.add(
            Report(
                tenant_id=tenant_id,
                id=report_id,
                review_id=review_id,
                snapshot_id=snapshot_id,
                kind="legacy",
                schema_version=2,
                content_digest=content,
                config_digest=_sha256_bytes(str(raw.get("completeness") or "").encode()),
                scope_summary={},
                provenance={"legacy": True, "import_id": str(import_id), "actor": LEGACY_NAME},
            )
        )
        session.flush()
        for change_id, local_id, rank in changes:
            session.add(
                ReportChange(
                    tenant_id=tenant_id,
                    report_id=report_id,
                    change_id=change_id,
                    review_id=review_id,
                    local_id=local_id,
                    rank_index=rank,
                    projection={"noise": False},
                )
            )
        review = session.get(Review, (tenant_id, review_id))
        if review is not None:
            review.latest_report_id = report_id
        session.flush()
        review_reports[review_id] = report_id
        if result is None and digest:
            warnings.append(f"result artifact missing or unreadable for review {review_id}")
    _ = legacy_id
    return review_reports


def _local_map(session: Session, tenant_id: UUID, report_id: UUID) -> dict[str, UUID]:
    rows = session.scalars(
        select(ReportChange).where(
            ReportChange.tenant_id == tenant_id,
            ReportChange.report_id == report_id,
        )
    )
    return {row.local_id: row.change_id for row in rows}


def _import_sessions(
    session: Session,
    root: Path,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    legacy_id: UUID,
    import_id: UUID,
    review_reports: dict[UUID, UUID],
    warnings: list[str],
) -> None:
    catalog_path = root / "browser.json"
    if not catalog_path.is_file():
        return
    sessions = _as_map(_read_json(catalog_path).get("sessions"))
    for key, raw in sessions.items():
        if not isinstance(raw, dict):
            continue
        review_id = _parse_uuid(key) or _parse_uuid(raw.get("review_id"))
        if review_id is None:
            warnings.append("session missing review_id")
            continue
        report_id = review_reports.get(review_id)
        statuses = _as_map(raw.get("statuses"))
        notes = _as_map(raw.get("notes"))
        if report_id is None:
            for local_id, status in statuses.items():
                _attach_unattached(
                    session,
                    tenant_id=tenant_id,
                    import_id=import_id,
                    review_ref=str(review_id),
                    change_ref=str(local_id),
                    kind="decision",
                    payload={"status": status},
                    reason="missing-report",
                )
            for local_id, text in notes.items():
                _attach_unattached(
                    session,
                    tenant_id=tenant_id,
                    import_id=import_id,
                    review_ref=str(review_id),
                    change_ref=str(local_id),
                    kind="note",
                    payload={"text": text},
                    reason="missing-report",
                )
            warnings.append(f"session for {review_id} has no imported report")
            continue
        mapping = _local_map(session, tenant_id, report_id)
        for local_id, raw_status in statuses.items():
            change_id = mapping.get(str(local_id))
            status = _valid_status(raw_status)
            if change_id is None:
                _attach_unattached(
                    session,
                    tenant_id=tenant_id,
                    import_id=import_id,
                    review_ref=str(review_id),
                    change_ref=str(local_id),
                    kind="decision",
                    payload={"status": raw_status},
                    reason="missing-change",
                )
                warnings.append(f"unattached decision {review_id}:{local_id}")
                continue
            if status is None:
                _attach_unattached(
                    session,
                    tenant_id=tenant_id,
                    import_id=import_id,
                    review_ref=str(review_id),
                    change_ref=str(local_id),
                    kind="conflict",
                    payload={"status": raw_status},
                    reason="unknown-status",
                )
                warnings.append(f"unknown status for {review_id}:{local_id}")
                continue
            _set_decision(
                session,
                tenant_id=tenant_id,
                review_id=review_id,
                report_id=report_id,
                change_id=change_id,
                actor_id=legacy_id,
                status=status,
            )
        for local_id, text in notes.items():
            change_id = mapping.get(str(local_id))
            if change_id is None:
                _attach_unattached(
                    session,
                    tenant_id=tenant_id,
                    import_id=import_id,
                    review_ref=str(review_id),
                    change_ref=str(local_id),
                    kind="note",
                    payload={"text": text},
                    reason="missing-change",
                )
                warnings.append(f"unattached note {review_id}:{local_id}")
                continue
            _set_note(
                session,
                tenant_id=tenant_id,
                review_id=review_id,
                report_id=report_id,
                change_id=change_id,
                actor_id=legacy_id,
                text=str(text),
            )
        if session.get(PersonalSession, (tenant_id, actor_id, review_id, "tui")) is None:
            history = raw.get("history")
            session.add(
                PersonalSession(
                    tenant_id=tenant_id,
                    user_id=actor_id,
                    review_id=review_id,
                    client_kind="tui",
                    report_id=report_id,
                    selection={
                        "selected_id": raw.get("selected_id"),
                        "selected_file": raw.get("selected_file"),
                        "lens": raw.get("lens") or "overview",
                        "focused_pane": raw.get("focused_pane") or "navigator",
                        "search": raw.get("search") or "",
                    },
                    history=history if isinstance(history, list) else [],
                    version=1,
                )
            )
        session.flush()


def _import_jsonstore(
    session: Session,
    root: Path,
    *,
    tenant_id: UUID,
    legacy_id: UUID,
    import_id: UUID,
    review_reports: dict[UUID, UUID],
    warnings: list[str],
) -> None:
    path = root / "review.json"
    if not path.is_file():
        return
    data = _read_json(path)
    decisions = _as_map(data.get("decisions"))
    for raw in decisions.values():
        if not isinstance(raw, dict):
            continue
        review_id = _parse_uuid(raw.get("review_id"))
        change_ref = str(raw.get("change_id") or "")
        status = _valid_status(raw.get("status"))
        if review_id is None:
            continue
        report_id = review_reports.get(review_id)
        change_id = _parse_uuid(change_ref)
        mapping = _local_map(session, tenant_id, report_id) if report_id is not None else {}
        resolved = None
        if change_id is not None and report_id is not None:
            if session.get(ReportChange, (tenant_id, report_id, change_id)) is not None:
                resolved = change_id
        if resolved is None and change_ref in mapping:
            resolved = mapping[change_ref]
        if report_id is None or resolved is None:
            _attach_unattached(
                session,
                tenant_id=tenant_id,
                import_id=import_id,
                review_ref=str(review_id),
                change_ref=change_ref,
                kind="decision" if status is not None else "conflict",
                payload=dict(raw),
                reason="unresolved-jsonstore-decision",
            )
            warnings.append(f"jsonstore decision {review_id}:{change_ref} is unattached")
            continue
        current = session.get(Decision, (tenant_id, report_id, resolved))
        if current is not None and status is not None and current.status != status:
            _attach_unattached(
                session,
                tenant_id=tenant_id,
                import_id=import_id,
                review_ref=str(review_id),
                change_ref=change_ref,
                kind="conflict",
                payload={"session": current.status, "store": status},
                reason="ambiguous-status",
            )
            warnings.append(f"ambiguous status for {review_id}:{change_ref}")
            _set_decision(
                session,
                tenant_id=tenant_id,
                review_id=review_id,
                report_id=report_id,
                change_id=resolved,
                actor_id=legacy_id,
                status=ReviewStatus.UNREVIEWED.value,
            )
            continue
        if status is None:
            warnings.append(f"unknown jsonstore status for {review_id}:{change_ref}")
            continue
        if current is None:
            _set_decision(
                session,
                tenant_id=tenant_id,
                review_id=review_id,
                report_id=report_id,
                change_id=resolved,
                actor_id=legacy_id,
                status=status,
            )
    notes = _as_map(data.get("notes"))
    for raw in notes.values():
        if not isinstance(raw, dict):
            continue
        review_id = _parse_uuid(raw.get("review_id"))
        _attach_unattached(
            session,
            tenant_id=tenant_id,
            import_id=import_id,
            review_ref=str(review_id or ""),
            change_ref="",
            kind="note",
            payload={"text": raw.get("text")},
            reason="review-level-note",
        )


def _import_prefs(
    session: Session,
    prefs_root: Path,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    import_id: UUID,
    warnings: list[str],
) -> None:
    store = PrefsStore(root=prefs_root)
    builtins = {item.name for item in BUILTIN_PRESETS}
    preference = session.get(Preference, (tenant_id, actor_id))
    if preference is None:
        preference = Preference(
            tenant_id=tenant_id,
            user_id=actor_id,
            disabled_repositories=sorted(store.load_disabled_repos()),
            last_scope_selection=store.load_selection().model_dump(mode="json"),
        )
        session.add(preference)
    presets_path = prefs_root / "presets.json"
    raw_presets: list[object] = []
    if presets_path.is_file():
        try:
            parsed = json.loads(presets_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"unreadable presets: {exc}")
            parsed = []
        if isinstance(parsed, list):
            raw_presets = parsed
    for item in raw_presets:
        if not isinstance(item, dict):
            continue
        try:
            preset = ScopePreset.model_validate(item)
        except Exception:
            session.add(
                LegacyHumanWork(
                    tenant_id=tenant_id,
                    id=uuid4(),
                    import_id=import_id,
                    original_review_ref="",
                    original_change_ref=str(item.get("name") or ""),
                    kind="conflict",
                    payload={str(key): value for key, value in item.items()},
                    reason="unknown-preset-fields",
                )
            )
            warnings.append(f"unknown preset fields in {item.get('name')}")
            continue
        name = f"{preset.name} (imported)" if preset.name in builtins else preset.name
        normalized = name.casefold()
        exists = session.scalar(
            select(Preset).where(
                Preset.tenant_id == tenant_id,
                Preset.user_id == actor_id,
                Preset.normalized_name == normalized,
            )
        )
        if exists is not None:
            continue
        session.add(
            Preset(
                tenant_id=tenant_id,
                user_id=actor_id,
                id=uuid4(),
                name=name,
                normalized_name=normalized,
                selection={"enabled": preset.enabled, "models": preset.models},
                version=1,
            )
        )


def _completed_result(
    row: MigrationImport,
    *,
    actor_id: UUID,
    backup_dir: Path | None,
    dry_run: bool = False,
) -> ImportResult:
    warnings_raw = row.counts.get("warnings")
    warnings = [str(item) for item in warnings_raw] if isinstance(warnings_raw, list) else []
    return ImportResult(
        import_id=row.import_id,
        tenant_id=row.destination_tenant_id,
        actor_id=actor_id,
        backup_dir=backup_dir,
        state=row.state,
        counts=dict(row.counts),
        warnings=warnings,
        dry_run=dry_run,
        source_fingerprint=row.source_fingerprint,
    )


def _actor_from_counts(counts: dict[str, object], fallback: UUID) -> UUID:
    parsed = _parse_uuid(counts.get("actor_id"))
    return parsed if parsed is not None else fallback


def import_legacy_root(
    root: Path,
    *,
    apply: bool = True,
    prefs_root: Path | None = None,
) -> ImportResult:
    root = root.resolve()
    _inspect_legacy(root)
    fingerprint = source_fingerprint(root)
    if not apply:
        return ImportResult(
            import_id=uuid4(),
            tenant_id=uuid4(),
            actor_id=uuid4(),
            backup_dir=None,
            state="dry-run",
            counts={"fingerprint": fingerprint},
            dry_run=True,
            source_fingerprint=fingerprint,
        )
    try:
        with _migration_lock(root):
            return _import_locked(root, fingerprint=fingerprint, prefs_root=prefs_root)
    except OSError as exc:
        raise ImportError(f"unable to migrate {root}: {exc}") from exc


def _import_locked(root: Path, *, fingerprint: str, prefs_root: Path | None) -> ImportResult:
    marker = None
    try:
        marker = read_marker(root)
    except BackendIncompatibleError:
        raise ImportRefused("database schema is newer than application") from None
    if marker is not None:
        engine = create_sqlite_engine(database_file(root, marker))
        db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
        try:
            row = db.get(MigrationImport, marker.import_id)
            if row is None:
                raise ImportRefused("backend marker does not match an import record")
            if row.source_fingerprint != fingerprint:
                raise ImportRefused("source changed since the completed import")
            if row.state == "completed":
                return _completed_result(
                    row,
                    actor_id=marker.actor_id,
                    backup_dir=None,
                )
        finally:
            db.close()
            engine.dispose()
    sqlite_path = root / DATABASE_NAME
    if sqlite_path.is_file() and marker is None:
        engine = create_sqlite_engine(sqlite_path)
        db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
        try:
            row = db.scalar(select(MigrationImport).order_by(MigrationImport.created_at.desc()))
            if row is not None and row.source_fingerprint != fingerprint:
                raise ImportRefused("source changed since the interrupted import")
            if row is not None and row.state == "completed":
                actor_id = _actor_from_counts(row.counts, uuid4())
                write_marker(
                    root,
                    BackendMarker(
                        backend=BACKEND_SQL,
                        schema_generation=SCHEMA_GENERATION,
                        import_id=row.import_id,
                        tenant_id=row.destination_tenant_id,
                        actor_id=actor_id,
                        min_app_version=MIN_APP_VERSION,
                        database=DATABASE_NAME,
                    ),
                )
                return _completed_result(row, actor_id=actor_id, backup_dir=None)
        finally:
            db.close()
            engine.dispose()
    backup = _backup_root(root)
    engine = create_sqlite_engine(sqlite_path)
    initialize_engine(engine)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    try:
        tenant_id, actor_id, legacy_id = _ensure_identities(db)
        existing = db.scalar(
            select(MigrationImport).where(MigrationImport.source_fingerprint == fingerprint)
        )
        import_row = existing or MigrationImport(
            import_id=uuid4(),
            source_fingerprint=fingerprint,
            destination_tenant_id=tenant_id,
            state="importing",
            counts={},
            validation_digest=EMPTY_DIGEST,
        )
        if existing is None:
            db.add(import_row)
            db.flush()
        warnings: list[str] = []
        review_reports = _import_catalog(
            db,
            root,
            tenant_id=tenant_id,
            actor_id=actor_id,
            legacy_id=legacy_id,
            import_id=import_row.import_id,
            warnings=warnings,
        )
        _import_sessions(
            db,
            root,
            tenant_id=tenant_id,
            actor_id=actor_id,
            legacy_id=legacy_id,
            import_id=import_row.import_id,
            review_reports=review_reports,
            warnings=warnings,
        )
        _import_jsonstore(
            db,
            root,
            tenant_id=tenant_id,
            legacy_id=legacy_id,
            import_id=import_row.import_id,
            review_reports=review_reports,
            warnings=warnings,
        )
        _import_prefs(
            db,
            prefs_root or root,
            tenant_id=tenant_id,
            actor_id=actor_id,
            import_id=import_row.import_id,
            warnings=warnings,
        )
        unattached = len(
            db.scalars(
                select(LegacyHumanWork).where(
                    LegacyHumanWork.tenant_id == tenant_id,
                    LegacyHumanWork.import_id == import_row.import_id,
                )
            ).all()
        )
        counts: dict[str, object] = {
            "reviews": len(review_reports),
            "reports": len(set(review_reports.values())),
            "unattached": unattached,
            "warnings": warnings,
            "actor_id": str(actor_id),
            "backup": str(backup),
        }
        import_row.counts = counts
        import_row.state = "completed"
        import_row.completed_at = utcnow()
        import_row.validation_digest = _sha256_bytes(
            json.dumps(counts, sort_keys=True, default=str).encode()
        )
        db.commit()
        write_marker(
            root,
            BackendMarker(
                backend=BACKEND_SQL,
                schema_generation=SCHEMA_GENERATION,
                import_id=import_row.import_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                min_app_version=MIN_APP_VERSION,
                database=DATABASE_NAME,
            ),
        )
        for name in ("browser.json", "review.json"):
            path = root / name
            if path.is_file():
                path.chmod(0o444)
        return ImportResult(
            import_id=import_row.import_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            backup_dir=backup,
            state="completed",
            counts=counts,
            warnings=warnings,
            source_fingerprint=fingerprint,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        engine.dispose()
