from __future__ import annotations

from pathlib import Path

from harpy.git.worktree import WorktreeManager
from harpy.proc import run


def _git_repo(path: Path) -> str:
    path.mkdir(parents=True)
    run(["git", "init"], cwd=path, timeout=10)
    run(["git", "config", "user.email", "t@t.test"], cwd=path, timeout=5)
    run(["git", "config", "user.name", "t"], cwd=path, timeout=5)
    (path / "a.py").write_text("x = 1\n", encoding="utf-8")
    run(["git", "add", "a.py"], cwd=path, timeout=5)
    run(["git", "commit", "-m", "init"], cwd=path, timeout=10)
    sha = run(["git", "rev-parse", "HEAD"], cwd=path, timeout=5)
    assert sha.ok
    return sha.stdout.strip()


def test_ensure_reuses_local_source(tmp_path: Path) -> None:
    source = tmp_path / "src"
    sha = _git_repo(source)
    manager = WorktreeManager(tmp_path / "cache")
    first = manager.ensure("local", sha, source=source)
    assert (first / "a.py").is_file()
    again = manager.ensure("local", sha, source=source)
    assert again == first
