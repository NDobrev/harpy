"""Immutable revision snapshots and canonical aggregate diffs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from harpy.git.diff import parse_unified_diff
from harpy.models import FileManifestEntry, RevisionSnapshot
from harpy.proc import run


class SnapshotError(RuntimeError):
    pass


class MovingHeadError(SnapshotError):
    pass


class SnapshotMeta:
    def __init__(
        self,
        *,
        base_tip_sha: str,
        comparison_base_sha: str,
        head_sha: str,
        title: str = "",
        body: str = "",
        target_id: UUID | None = None,
    ) -> None:
        self.base_tip_sha = base_tip_sha
        self.comparison_base_sha = comparison_base_sha
        self.head_sha = head_sha
        self.title = title
        self.body = body
        self.target_id = target_id or uuid4()


def merge_base(repo: Path, tip: str, head: str) -> str:
    result = run(["git", "merge-base", tip, head], cwd=repo, timeout=10)
    if not result.ok:
        raise SnapshotError(result.stderr.strip() or "merge-base failed")
    return result.stdout.strip()


def canonical_diff(repo: Path, base: str, head: str) -> str:
    result = run(
        [
            "git",
            "-c",
            "diff.noprefix=false",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--find-renames",
            f"{base}..{head}",
        ],
        cwd=repo,
        timeout=30,
    )
    if not result.ok:
        raise SnapshotError(result.stderr.strip() or "git diff failed")
    return result.stdout


def inventory_from_diff(raw: str) -> list[FileManifestEntry]:
    entries: list[FileManifestEntry] = []
    for file in parse_unified_diff(raw):
        kind = "file"
        if file.is_submodule:
            kind = "submodule"
        elif file.is_binary:
            kind = "binary"
        elif file.status == "renamed" and not file.hunks:
            kind = "rename"
        elif file.mode_change and not file.hunks:
            kind = "mode"
        entries.append(
            FileManifestEntry(
                path=file.path,
                old_path=file.old_path,
                file_kind=kind,
                mode="160000" if file.is_submodule else "",
                binary=file.is_binary,
                source_available=not file.is_binary and not file.is_submodule,
            )
        )
    return entries


def snapshot_from_diff(meta: SnapshotMeta, raw: str) -> RevisionSnapshot:
    digest = sha256(raw.encode("utf-8")).hexdigest()
    return RevisionSnapshot(
        id=uuid4(),
        target_id=meta.target_id,
        base_tip_sha=meta.base_tip_sha,
        comparison_base_sha=meta.comparison_base_sha,
        head_sha=meta.head_sha,
        title=meta.title,
        body=meta.body,
        file_manifest=inventory_from_diff(raw),
        diff_digest=digest,
        created_at=datetime.now(UTC),
        acquisition_complete=True,
    )


def acquire_github_snapshot(
    fetch_meta: Callable[[], SnapshotMeta],
    capture: Callable[[SnapshotMeta], RevisionSnapshot],
) -> RevisionSnapshot:
    first = fetch_meta()
    snapshot = capture(first)
    second = fetch_meta()
    if (second.head_sha, second.base_tip_sha, second.comparison_base_sha) == (
        first.head_sha,
        first.base_tip_sha,
        first.comparison_base_sha,
    ):
        return snapshot
    snapshot = capture(second)
    third = fetch_meta()
    if (third.head_sha, third.base_tip_sha, third.comparison_base_sha) != (
        second.head_sha,
        second.base_tip_sha,
        second.comparison_base_sha,
    ):
        raise MovingHeadError("PR is moving")
    return snapshot


def capture_local_comparison(repo: Path, meta: SnapshotMeta) -> RevisionSnapshot:
    raw = canonical_diff(repo, meta.comparison_base_sha, meta.head_sha)
    return snapshot_from_diff(meta, raw)
