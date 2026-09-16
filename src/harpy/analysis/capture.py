"""Capture snapshots and publish immutable static reports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from harpy.analysis.pipeline import analyze_captured
from harpy.config import HarpyConfig
from harpy.git.diff import parse_unified_diff
from harpy.git.local import LocalCapture, LocalSpec, capture_local_stable
from harpy.git.snapshots import SnapshotMeta
from harpy.models import (
    AnalysisResult,
    ChangedFile,
    FileCategory,
    PullRequest,
    _require_repo_path,
)
from harpy.proc import run
from harpy.storage.schema import utcnow
from harpy.storage.workspace import TenantWorkspace

MAX_FILES = 20_000
MAX_HUNKS = 100_000
MAX_PATCH_BYTES = 50 * 1024 * 1024
MAX_TEXT_FILE = 10 * 1024 * 1024
NOISE = {FileCategory.GENERATED.value, FileCategory.LOCKFILE.value, FileCategory.SNAPSHOT.value}


class CaptureError(RuntimeError):
    pass


class InventoryLimit(CaptureError):
    pass


@dataclass(frozen=True)
class CaptureLimits:
    max_files: int = MAX_FILES
    max_hunks: int = MAX_HUNKS
    max_patch_bytes: int = MAX_PATCH_BYTES
    max_text_file: int = MAX_TEXT_FILE


@dataclass(frozen=True)
class CapturedBlob:
    available: bool
    data: bytes = b""
    reason: str | None = None
    symlink: bool = False
    submodule: bool = False


@dataclass(frozen=True)
class InboxHit:
    number: int
    title: str
    author: str
    repo: str = ""
    repository_id: UUID | None = None


@dataclass(frozen=True)
class InboxHits:
    rows: list[InboxHit]
    truncated: bool = False


class GithubSource(Protocol):
    login: str
    semantic_calls: int
    clone_calls: int

    def get_pr(self, number: int, *, repo: str) -> PullRequest: ...
    def get_diff(self, number: int, *, repo: str) -> str: ...
    def get_blob(self, sha: str, path: str) -> CapturedBlob: ...
    def search_prs(self, tab: str, *, open_only: bool, login: str) -> InboxHits: ...


@dataclass
class FileCapture:
    path: str
    old_path: str | None
    kind: str
    mode: str
    binary: bool
    base_bytes: bytes | None
    head_bytes: bytes | None
    base_available: bool
    head_available: bool
    availability_reason: str | None
    byte_size: int


@dataclass
class CaptureBundle:
    base_tip_sha: str | None
    comparison_base_sha: str | None
    head_sha: str | None
    local_digest: str | None
    intent_digest: str
    manifest_digest: str
    diff_digest: str
    patch: bytes
    files: list[FileCapture]
    changed: list[ChangedFile]
    title: str
    body: str
    author: str | None = None
    pr_state: str | None = None
    texts: dict[str, str] = field(default_factory=dict)


def _digest(payload: bytes | str) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return sha256(payload).hexdigest()


def _file_kind(file: ChangedFile) -> str:
    if file.is_submodule:
        return "submodule"
    if file.is_binary:
        return "binary"
    if file.status == "renamed":
        return "rename"
    if file.mode_change and not file.hunks:
        return "mode"
    return "file"


def _side_state(
    file: ChangedFile,
    blob: CapturedBlob | None,
    *,
    side: str,
    limits: CaptureLimits,
) -> tuple[bytes | None, bool, str | None]:
    if side == "base" and file.status == "added":
        return None, False, "absent_side"
    if side == "head" and file.status == "deleted":
        return None, False, "absent_side"
    if file.is_submodule:
        return None, False, "submodule"
    if file.is_binary:
        return None, False, "binary"
    if blob is None:
        return None, False, "missing_snapshot"
    if blob.submodule:
        return None, False, "submodule"
    if blob.symlink:
        return None, False, "symlink"
    if not blob.available:
        return None, False, blob.reason or "missing_snapshot"
    if len(blob.data) > limits.max_text_file:
        return None, False, "size_limit"
    try:
        blob.data.decode("utf-8")
    except UnicodeDecodeError:
        return None, False, "unsupported_encoding"
    return blob.data, True, None


def _combine_reason(base: str | None, head: str | None) -> str | None:
    return head or base


def _read_git_blob(repo: Path, revision: str | None, relative: str) -> CapturedBlob:
    if not revision:
        return CapturedBlob(False, reason="absent_side")
    try:
        path = _require_repo_path(relative)
    except ValueError:
        return CapturedBlob(False, reason="missing_snapshot")
    listed = run(["git", "ls-tree", "-z", revision, "--", path], cwd=repo, timeout=10)
    if not listed.ok or not listed.stdout.strip():
        return CapturedBlob(False, reason="absent_side")
    meta = listed.stdout.split("\0", 1)[0]
    mode = meta.split(" ", 1)[0]
    if mode == "160000":
        return CapturedBlob(False, reason="submodule", submodule=True)
    if mode == "120000":
        return CapturedBlob(False, reason="symlink", symlink=True)
    shown = run(["git", "show", f"{revision}:{path}"], cwd=repo, timeout=10)
    if not shown.ok:
        return CapturedBlob(False, reason="missing_snapshot")
    return CapturedBlob(True, data=shown.stdout.encode("utf-8"))


def _read_worktree_blob(repo: Path, relative: str) -> CapturedBlob:
    try:
        path = _require_repo_path(relative)
    except ValueError:
        return CapturedBlob(False, reason="missing_snapshot")
    candidate = (repo / path).resolve()
    if not candidate.is_relative_to(repo.resolve()):
        return CapturedBlob(False, reason="missing_snapshot")
    if (repo / path).is_symlink():
        return CapturedBlob(False, reason="symlink", symlink=True)
    if not candidate.is_file():
        return CapturedBlob(False, reason="absent_side")
    return CapturedBlob(True, data=candidate.read_bytes())


def _read_index_blob(repo: Path, relative: str) -> CapturedBlob:
    try:
        path = _require_repo_path(relative)
    except ValueError:
        return CapturedBlob(False, reason="missing_snapshot")
    listed = run(["git", "ls-files", "--stage", "--", path], cwd=repo, timeout=10)
    if not listed.ok or not listed.stdout.strip():
        return CapturedBlob(False, reason="absent_side")
    mode = listed.stdout.split(" ", 1)[0]
    if mode == "160000":
        return CapturedBlob(False, reason="submodule", submodule=True)
    if mode == "120000":
        return CapturedBlob(False, reason="symlink", symlink=True)
    shown = run(["git", "show", f":{path}"], cwd=repo, timeout=10)
    if not shown.ok:
        return CapturedBlob(False, reason="missing_snapshot")
    return CapturedBlob(True, data=shown.stdout.encode("utf-8"))


def assemble_bundle(
    *,
    patch: str,
    title: str,
    body: str,
    base_tip_sha: str | None,
    comparison_base_sha: str | None,
    head_sha: str | None,
    local_digest: str | None,
    limits: CaptureLimits,
    reader: Callable[[str, str], CapturedBlob],
    author: str | None = None,
    pr_state: str | None = None,
) -> CaptureBundle:
    encoded = patch.encode("utf-8")
    if len(encoded) > limits.max_patch_bytes:
        raise InventoryLimit("patch exceeds capture limit")
    changed = parse_unified_diff(patch)
    if len(changed) > limits.max_files:
        raise InventoryLimit("file inventory exceeds capture limit")
    hunks = sum(len(item.hunks) for item in changed)
    if hunks > limits.max_hunks:
        raise InventoryLimit("hunk inventory exceeds capture limit")
    files: list[FileCapture] = []
    texts: dict[str, str] = {}
    manifest: list[dict[str, object]] = []
    for item in changed:
        try:
            _require_repo_path(item.path)
        except ValueError as exc:
            raise CaptureError(str(exc)) from exc
        base_blob = reader(item.old_path or item.path, "base")
        head_blob = reader(item.path, "head")
        base_bytes, base_ok, base_reason = _side_state(item, base_blob, side="base", limits=limits)
        head_bytes, head_ok, head_reason = _side_state(item, head_blob, side="head", limits=limits)
        reason = _combine_reason(base_reason, head_reason)
        if head_ok and head_bytes is not None:
            texts[item.path] = head_bytes.decode("utf-8")
        files.append(
            FileCapture(
                path=item.path,
                old_path=item.old_path,
                kind=_file_kind(item),
                mode="160000" if item.is_submodule else "",
                binary=item.is_binary,
                base_bytes=base_bytes,
                head_bytes=head_bytes,
                base_available=base_ok,
                head_available=head_ok,
                availability_reason=reason,
                byte_size=len(head_bytes or base_bytes or b""),
            )
        )
        manifest.append({"path": item.path, "old_path": item.old_path, "kind": _file_kind(item)})
    intent = _digest(dumps({"title": title, "body": body}, sort_keys=True))
    return CaptureBundle(
        base_tip_sha=base_tip_sha,
        comparison_base_sha=comparison_base_sha,
        head_sha=head_sha,
        local_digest=local_digest,
        intent_digest=intent,
        manifest_digest=_digest(dumps(manifest, sort_keys=True)),
        diff_digest=_digest(encoded),
        patch=encoded,
        files=files,
        changed=changed,
        title=title,
        body=body,
        author=author,
        pr_state=pr_state,
        texts=texts,
    )


def capture_github(
    source: GithubSource,
    *,
    repo: str,
    number: int,
    limits: CaptureLimits,
) -> CaptureBundle:
    def meta() -> SnapshotMeta:
        pr = source.get_pr(number, repo=repo)
        return SnapshotMeta(
            base_tip_sha=pr.base_sha or pr.base_ref,
            comparison_base_sha=pr.base_sha or pr.base_ref,
            head_sha=pr.head_sha,
            title=pr.title,
            body=pr.body,
        )

    def _capture(first: SnapshotMeta) -> CaptureBundle:
        pr = source.get_pr(number, repo=repo)
        patch = source.get_diff(number, repo=repo)

        def reader(path: str, side: str) -> CapturedBlob:
            sha = first.head_sha if side == "head" else first.comparison_base_sha
            return source.get_blob(sha, path)

        return assemble_bundle(
            patch=patch,
            title=pr.title,
            body=pr.body,
            base_tip_sha=pr.base_sha or first.base_tip_sha,
            comparison_base_sha=pr.base_sha or first.comparison_base_sha,
            head_sha=pr.head_sha,
            local_digest=None,
            limits=limits,
            reader=reader,
            author=source.login,
            pr_state=pr.state,
        )

    first = meta()
    bundle = _capture(first)
    second = meta()
    if (second.head_sha, second.base_tip_sha) != (first.head_sha, first.base_tip_sha):
        bundle = _capture(second)
        third = meta()
        if (third.head_sha, third.base_tip_sha) != (second.head_sha, second.base_tip_sha):
            raise CaptureError("PR is moving")
    return bundle


def capture_local_repo(
    repo: Path,
    spec: LocalSpec,
    *,
    limits: CaptureLimits,
    title: str,
) -> CaptureBundle:
    captured: LocalCapture = capture_local_stable(repo, spec)

    def reader(path: str, side: str) -> CapturedBlob:
        if spec.mode == "committed":
            revision = captured.head_sha if side == "head" else captured.comparison_base_sha
            return _read_git_blob(repo, revision, path)
        if spec.mode == "staged":
            if side == "head":
                return _read_index_blob(repo, path)
            return _read_git_blob(repo, captured.comparison_base_sha, path)
        if side == "head":
            return _read_worktree_blob(repo, path)
        return _read_git_blob(repo, captured.comparison_base_sha, path)

    return assemble_bundle(
        patch=captured.patch,
        title=title,
        body="",
        base_tip_sha=captured.base_tip_sha,
        comparison_base_sha=captured.comparison_base_sha,
        head_sha=captured.head_sha,
        local_digest=captured.local_digest,
        limits=limits,
        reader=reader,
    )


def _projection(
    change_id: UUID, local_id: str, rank: int, result: AnalysisResult
) -> dict[str, object]:
    match = next((item for item in result.changes if item.id == local_id), result.changes[rank])
    category = ""
    if match.files:
        file = next((item for item in result.files if item.path == match.files[0]), None)
        if file is not None and file.category_scores:
            category = max(file.category_scores, key=lambda key: file.category_scores[key])
    return {
        "title": match.title,
        "importance": match.importance,
        "unexpectedness": match.unexpectedness,
        "confidence": match.confidence,
        "risk": match.risk.lower(),
        "file_count": len(match.files),
        "hunk_count": len(match.hunk_ids or match.hunks),
        "noise": category in NOISE,
        "paths": list(match.files),
        "hunk_ids": list(match.hunk_ids or match.hunks),
        "symbols": list(match.affected_symbols),
        "before": match.before,
        "after": match.after,
        "why": match.why,
        "consequence": match.business_effect,
        "change_id": str(change_id),
    }


def publish_static(
    workspace: TenantWorkspace,
    *,
    review_id: UUID,
    bundle: CaptureBundle,
    config: HarpyConfig,
) -> UUID:
    pr = PullRequest(
        number=0,
        title=bundle.title,
        body=bundle.body,
        base_ref=bundle.base_tip_sha or "",
        head_ref=bundle.head_sha or bundle.local_digest or "",
        head_sha=bundle.head_sha or "",
        base_sha=bundle.comparison_base_sha or "",
        additions=sum(item.additions for item in bundle.changed),
        deletions=sum(item.deletions for item in bundle.changed),
        state=bundle.pr_state or "",
    )
    result = analyze_captured(pr, bundle.changed, config=config, texts=bundle.texts)
    patch = workspace.put_artifact("patch", bundle.patch)
    snapshot_id = uuid4()
    file_rows: list[dict[str, object]] = []
    for item in bundle.files:
        base_digest = (
            workspace.put_artifact("source", item.base_bytes).digest
            if item.base_bytes is not None
            else None
        )
        head_digest = (
            workspace.put_artifact("source", item.head_bytes).digest
            if item.head_bytes is not None
            else None
        )
        file_rows.append(
            {
                "id": uuid4(),
                "path": item.path,
                "old_path": item.old_path,
                "kind": item.kind,
                "mode": item.mode,
                "base_artifact": base_digest,
                "head_artifact": head_digest,
                "base_available": item.base_available,
                "head_available": item.head_available,
                "availability_reason": item.availability_reason,
                "binary": item.binary,
                "byte_size": item.byte_size,
            }
        )
    workspace.add_snapshot(
        snapshot_id=snapshot_id,
        review_id=review_id,
        bundle={
            "base_tip_sha": bundle.base_tip_sha,
            "comparison_base_sha": bundle.comparison_base_sha,
            "head_sha": bundle.head_sha,
            "local_digest": bundle.local_digest,
            "intent_digest": bundle.intent_digest,
            "manifest_digest": bundle.manifest_digest,
            "diff_digest": patch.digest,
            "acquisition_status": "complete",
        },
        files=file_rows,
    )
    changes: list[tuple[UUID, str, int, dict[str, object]]] = []
    for index, change in enumerate(result.changes):
        change_id = uuid4()
        changes.append(
            (change_id, change.id, index, _projection(change_id, change.id, index, result))
        )
    report = workspace.publish_static_report(
        review_id=review_id,
        snapshot_id=snapshot_id,
        content_digest=_digest(dumps({"diff": patch.digest, "changes": [c[1] for c in changes]})),
        config_digest=_digest(config.semantic.model),
        changes=changes,
        scope_summary={"changes": {"status": "complete", "provenance": "new"}},
        provenance={"kind": "static", "semantic_calls": 0},
        observation={
            "head_sha": bundle.head_sha,
            "local_digest": bundle.local_digest,
            "intent_digest": bundle.intent_digest,
            "base_tip_sha": bundle.base_tip_sha,
            "title": bundle.title,
            "author": bundle.author,
            "pr_state": bundle.pr_state,
            "observed_at": utcnow().isoformat(),
        },
    )
    return report.id
