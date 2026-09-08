"""Immutable source reads bound to a snapshot root or Git revision."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harpy.models import _require_repo_path
from harpy.proc import run


@dataclass(frozen=True)
class SourceRead:
    path: str
    side: str
    available: bool
    text: str = ""
    reason: str = ""
    is_symlink: bool = False


def _invalid(path: str, side: str, reason: str) -> SourceRead:
    return SourceRead(path=path, side=side, available=False, reason=reason)


def read_snapshot_path(root: Path, relative: str, *, side: str = "head") -> SourceRead:
    try:
        path = _require_repo_path(relative)
    except ValueError as exc:
        return _invalid(relative, side, str(exc))
    base = root.resolve()
    candidate = base / path
    if candidate.is_symlink():
        target = candidate.resolve()
        if not target.is_relative_to(base):
            return _invalid(path, side, "symlink escapes snapshot")
        return SourceRead(path=path, side=side, available=False, reason="symlink", is_symlink=True)
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        return _invalid(path, side, str(exc))
    if not resolved.is_relative_to(base):
        return _invalid(path, side, "path escapes snapshot")
    if not resolved.is_file():
        return _invalid(path, side, "not a file")
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _invalid(path, side, str(exc))
    return SourceRead(path=path, side=side, available=True, text=text)


def read_git_blob(repo: Path, revision: str, relative: str, *, side: str) -> SourceRead:
    try:
        path = _require_repo_path(relative)
    except ValueError as exc:
        return _invalid(relative, side, str(exc))
    if ".." in revision or revision.startswith("-"):
        return _invalid(path, side, "invalid revision")
    result = run(
        ["git", "-c", "core.quotepath=false", "show", f"{revision}:{path}"],
        cwd=repo,
        timeout=10,
    )
    if not result.ok:
        return _invalid(path, side, result.stderr.strip() or "blob unavailable")
    return SourceRead(path=path, side=side, available=True, text=result.stdout)
