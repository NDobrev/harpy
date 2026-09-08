"""Local committed, staged, and working-tree comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harpy.git.snapshots import SnapshotMeta, canonical_diff, merge_base, snapshot_from_diff
from harpy.models import RevisionSnapshot
from harpy.proc import run


@dataclass(frozen=True)
class LocalSpec:
    mode: str
    base: str | None = None
    include_untracked: bool = False


class LocalReviewError(RuntimeError):
    pass


def parse_local_args(
    *,
    local: bool,
    base: str | None,
    staged: bool,
    working_tree: bool,
    include_untracked: bool,
) -> LocalSpec:
    if not local:
        raise LocalReviewError("not a local review")
    chosen = [bool(base), staged, working_tree]
    if sum(chosen) != 1:
        raise LocalReviewError("require one comparison mode")
    if base:
        return LocalSpec(mode="committed", base=base)
    if staged:
        return LocalSpec(mode="staged")
    return LocalSpec(mode="working-tree", include_untracked=include_untracked)


def _rev_parse(repo: Path, rev: str) -> str:
    result = run(["git", "rev-parse", rev], cwd=repo, timeout=10)
    if not result.ok:
        raise LocalReviewError(result.stderr.strip() or f"unknown revision {rev}")
    return result.stdout.strip()


def capture_local(repo: Path, spec: LocalSpec) -> RevisionSnapshot:
    if spec.mode == "committed":
        assert spec.base is not None
        head = _rev_parse(repo, "HEAD")
        base = merge_base(repo, spec.base, "HEAD")
        raw = canonical_diff(repo, base, head)
        return snapshot_from_diff(
            SnapshotMeta(base_tip_sha=spec.base, comparison_base_sha=base, head_sha=head),
            raw,
        )
    if spec.mode == "staged":
        head = _rev_parse(repo, "HEAD")
        result = run(
            ["git", "diff", "--cached", "--no-ext-diff", "--no-textconv"], cwd=repo, timeout=30
        )
        if not result.ok:
            raise LocalReviewError(result.stderr)
        return snapshot_from_diff(
            SnapshotMeta(base_tip_sha=head, comparison_base_sha=head, head_sha="INDEX"),
            result.stdout,
        )
    head = _rev_parse(repo, "HEAD")
    argv = ["git", "diff", "HEAD", "--no-ext-diff", "--no-textconv"]
    result = run(argv, cwd=repo, timeout=30)
    if not result.ok:
        raise LocalReviewError(result.stderr)
    raw = result.stdout
    if spec.include_untracked:
        extra = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo, timeout=10)
        raw += extra.stdout
    return snapshot_from_diff(
        SnapshotMeta(base_tip_sha=head, comparison_base_sha=head, head_sha="WORKTREE"),
        raw,
    )
