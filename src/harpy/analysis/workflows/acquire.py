"""Snapshot acquisition used by ReviewService."""

from __future__ import annotations

from pathlib import Path

from harpy.git.snapshots import (
    SnapshotMeta,
    capture_local_comparison,
    merge_base,
)
from harpy.git.source import SourceRead, read_git_blob, read_snapshot_path
from harpy.models import RevisionSnapshot


def source_for(
    *,
    snapshot: RevisionSnapshot | None = None,
    root: Path | None = None,
    repo: Path | None = None,
    path: str,
    side: str = "head",
) -> SourceRead:
    if root is not None:
        return read_snapshot_path(root, path, side=side)
    if repo is not None and snapshot is not None:
        revision = snapshot.head_sha if side == "head" else snapshot.comparison_base_sha
        return read_git_blob(repo, revision, path, side=side)
    return SourceRead(path=path, side=side, available=False, reason="no snapshot source")


def snapshot_for_local(repo: Path, base_ref: str, head: str = "HEAD") -> RevisionSnapshot:
    base = merge_base(repo, base_ref, head)
    meta = SnapshotMeta(
        base_tip_sha=base_ref,
        comparison_base_sha=base,
        head_sha=head,
    )
    return capture_local_comparison(repo, meta)
