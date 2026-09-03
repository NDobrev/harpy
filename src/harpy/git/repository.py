from __future__ import annotations

from pathlib import Path

from harpy.proc import run


def is_git_repo(path: Path | None = None) -> bool:
    result = run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=path,
        timeout=5,
    )
    return result.ok and result.stdout.strip() == "true"


def repo_identity(path: Path | None = None) -> str:
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=path, timeout=5)
    if not result.ok:
        return "unknown"
    top = Path(result.stdout.strip()).name
    remote = run(["git", "config", "--get", "remote.origin.url"], cwd=path, timeout=5)
    if remote.ok and remote.stdout.strip():
        url = remote.stdout.strip().rstrip("/").removesuffix(".git")
        return url.split(":")[-1].split("/")[-2] + "_" + url.split("/")[-1] if "/" in url else top
    return top
