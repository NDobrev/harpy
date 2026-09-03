"""Temporary worktrees reused by SHA."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from harpy.config import DEFAULT_CACHE_DIR
from harpy.proc import run


class WorktreeManager:
    def __init__(self, cache_dir: Path | None = None, ttl_seconds: float = 7 * 24 * 3600) -> None:
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.ttl_seconds = ttl_seconds

    def path_for(self, repo: str, sha: str) -> Path:
        safe = repo.replace("/", "_")
        return self.cache_dir / "worktrees" / safe / sha

    def clone_path(self, repo: str) -> Path:
        return self.cache_dir / "clones" / repo.replace("/", "_")

    def ensure(self, repo: str, sha: str, *, source: Path | None = None) -> Path:
        dest = self.path_for(repo, sha)
        if _is_checkout(dest):
            _stamp(dest)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source is not None and _add_worktree(dest, sha, cwd=source):
            _stamp(dest)
            return dest
        if "/" in repo:
            clone = self.ensure_origin_clone(repo)
            _fetch_sha(clone, sha)
            if _add_worktree(dest, sha, cwd=clone):
                _stamp(dest)
                return dest
        raise RuntimeError(f"cannot check out {repo}@{sha[:12]}")

    def ensure_origin_clone(self, repo: str) -> Path:
        clone = self.clone_path(repo)
        if (clone / "HEAD").is_file() and (clone / "objects").is_dir():
            return clone
        if clone.exists():
            shutil.rmtree(clone)
        clone.parent.mkdir(parents=True, exist_ok=True)
        result = run(
            ["gh", "repo", "clone", repo, str(clone), "--", "--bare"],
            timeout=180,
        )
        if not result.ok:
            raise RuntimeError(result.stderr.strip() or f"gh repo clone {repo} failed")
        return clone

    def cleanup(self, *, now: float | None = None) -> list[Path]:
        removed: list[Path] = []
        root = self.cache_dir / "worktrees"
        if not root.is_dir():
            return removed
        current = now if now is not None else time.time()
        for stamp in root.glob("*/*/.harpy-stamp"):
            try:
                age = current - float(stamp.read_text(encoding="utf-8").strip())
            except ValueError:
                age = self.ttl_seconds + 1
            if age > self.ttl_seconds:
                worktree = stamp.parent
                run(["git", "worktree", "remove", "--force", str(worktree)], timeout=30)
                removed.append(worktree)
        return removed


def _is_checkout(path: Path) -> bool:
    return path.is_dir() and (path / ".git").exists()


def _stamp(path: Path) -> None:
    path.joinpath(".harpy-stamp").write_text(str(time.time()), encoding="utf-8")


def _add_worktree(dest: Path, sha: str, *, cwd: Path) -> bool:
    result = run(["git", "worktree", "add", "--detach", str(dest), sha], cwd=cwd, timeout=60)
    return result.ok


def _fetch_sha(clone: Path, sha: str) -> None:
    fetched = run(["git", "fetch", "--depth", "1", "origin", sha], cwd=clone, timeout=120)
    if not fetched.ok:
        run(["git", "fetch", "origin"], cwd=clone, timeout=180)
