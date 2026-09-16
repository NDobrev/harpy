"""Local committed, staged, and working-tree comparisons."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from harpy.git.snapshots import SnapshotMeta, canonical_diff, merge_base, snapshot_from_diff
from harpy.models import RevisionSnapshot
from harpy.proc import run


@dataclass(frozen=True)
class LocalSpec:
    mode: str
    base: str | None = None
    include_untracked: bool = False


@dataclass(frozen=True)
class LocalCapture:
    base_tip_sha: str
    comparison_base_sha: str
    head_sha: str | None
    local_digest: str | None
    patch: str
    title: str = ""


class LocalReviewError(RuntimeError):
    pass


class UnsupportedComparison(LocalReviewError):
    pass


class RepositoryChanged(LocalReviewError):
    def __init__(self) -> None:
        super().__init__("Repository changed during capture")


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


def git_common_dir(repo: Path) -> str:
    result = run(["git", "rev-parse", "--git-common-dir"], cwd=repo, timeout=10)
    if not result.ok:
        raise LocalReviewError(result.stderr.strip() or "not a git repository")
    raw = result.stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = (repo / path).resolve()
    return str(path)


def _rev_parse(repo: Path, rev: str) -> str:
    result = run(["git", "rev-parse", "--verify", rev], cwd=repo, timeout=10)
    if not result.ok:
        raise LocalReviewError(result.stderr.strip() or f"unknown revision {rev}")
    return result.stdout.strip()


def _assert_supported(repo: Path) -> None:
    head = run(["git", "rev-parse", "--verify", "HEAD"], cwd=repo, timeout=10)
    if not head.ok:
        raise UnsupportedComparison("unborn repository")
    unmerged = run(["git", "ls-files", "--unmerged"], cwd=repo, timeout=10)
    if unmerged.ok and unmerged.stdout.strip():
        raise UnsupportedComparison("unmerged index")


def worktree_fingerprint(repo: Path, spec: LocalSpec) -> str:
    _assert_supported(repo)
    head = _rev_parse(repo, "HEAD")
    parts = [spec.mode, head]
    if spec.mode == "committed":
        assert spec.base is not None
        parts.append(_rev_parse(repo, spec.base))
        return sha256("\n".join(parts).encode("utf-8")).hexdigest()
    staged = run(["git", "ls-files", "-z", "--stage"], cwd=repo, timeout=10)
    parts.append(staged.stdout)
    if spec.mode == "working-tree":
        tracked = run(["git", "ls-files", "-z"], cwd=repo, timeout=10)
        names = [name for name in tracked.stdout.split("\0") if name]
        if spec.include_untracked:
            extra = run(
                ["git", "ls-files", "-z", "--others", "--exclude-standard"],
                cwd=repo,
                timeout=10,
            )
            names.extend(name for name in extra.stdout.split("\0") if name)
        digest = sha256()
        for path in sorted(set(names)):
            digest.update(path.encode("utf-8"))
            candidate = repo / path
            if candidate.is_symlink():
                digest.update(b"link:")
                digest.update(os_readlink(candidate).encode("utf-8", "replace"))
                continue
            if candidate.is_file():
                digest.update(candidate.read_bytes())
        parts.append(digest.hexdigest())
    return sha256("\n".join(parts).encode("utf-8")).hexdigest()


def os_readlink(path: Path) -> str:
    return path.readlink().as_posix()


def _untracked_patch(repo: Path, relative: str) -> str:
    candidate = repo / relative
    if candidate.is_symlink():
        target = os_readlink(candidate)
        return (
            f"diff --git a/{relative} b/{relative}\n"
            "new file mode 120000\n"
            "--- /dev/null\n"
            f"+++ b/{relative}\n"
            "@@ -0,0 +1 @@\n"
            f"+{target}\n"
        )
    if not candidate.is_file():
        return ""
    payload = candidate.read_bytes()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return (
            f"diff --git a/{relative} b/{relative}\n"
            "new file mode 100644\n"
            f"Binary files /dev/null and b/{relative} differ\n"
        )
    lines = text.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    missing_nl = "" if text.endswith("\n") or text == "" else "\n\\ No newline at end of file"
    count = max(len(lines), 1) if text else 0
    header = (
        f"diff --git a/{relative} b/{relative}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{relative}\n"
    )
    if count == 0:
        return header
    return f"{header}@@ -0,0 +{count} @@\n{body}{missing_nl}\n"


def _raw_diff(repo: Path, spec: LocalSpec) -> tuple[str, str, str, str | None]:
    _assert_supported(repo)
    head = _rev_parse(repo, "HEAD")
    if spec.mode == "committed":
        assert spec.base is not None
        base = merge_base(repo, spec.base, "HEAD")
        return canonical_diff(repo, base, head), spec.base, base, head
    if spec.mode == "staged":
        result = run(
            ["git", "diff", "--cached", "--no-ext-diff", "--no-textconv"], cwd=repo, timeout=30
        )
        if not result.ok:
            raise LocalReviewError(result.stderr)
        return result.stdout, head, head, None
    result = run(["git", "diff", "HEAD", "--no-ext-diff", "--no-textconv"], cwd=repo, timeout=30)
    if not result.ok:
        raise LocalReviewError(result.stderr)
    raw = result.stdout
    if spec.include_untracked:
        extra = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo, timeout=10)
        if extra.ok:
            for name in extra.stdout.splitlines():
                if name:
                    raw += _untracked_patch(repo, name)
    return raw, head, head, None


def capture_local_once(repo: Path, spec: LocalSpec) -> LocalCapture:
    raw, base_tip, comparison, head = _raw_diff(repo, spec)
    local_digest = None if spec.mode == "committed" else sha256(raw.encode("utf-8")).hexdigest()
    return LocalCapture(
        base_tip_sha=base_tip,
        comparison_base_sha=comparison,
        head_sha=head,
        local_digest=local_digest,
        patch=raw,
    )


def capture_local_stable(repo: Path, spec: LocalSpec) -> LocalCapture:
    first = worktree_fingerprint(repo, spec)
    captured = capture_local_once(repo, spec)
    if worktree_fingerprint(repo, spec) == first:
        return captured
    second = worktree_fingerprint(repo, spec)
    captured = capture_local_once(repo, spec)
    if worktree_fingerprint(repo, spec) != second:
        raise RepositoryChanged()
    if captured.local_digest is None:
        return captured
    return replace(captured, local_digest=second)


def capture_local(repo: Path, spec: LocalSpec) -> RevisionSnapshot:
    captured = capture_local_once(repo, spec)
    head = captured.head_sha or ("INDEX" if spec.mode == "staged" else "WORKTREE")
    return snapshot_from_diff(
        SnapshotMeta(
            base_tip_sha=captured.base_tip_sha,
            comparison_base_sha=captured.comparison_base_sha,
            head_sha=head,
        ),
        captured.patch,
    )
