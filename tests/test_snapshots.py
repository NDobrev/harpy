from __future__ import annotations

from pathlib import Path

from harpy.analysis.service import ReviewService
from harpy.config import HarpyConfig
from harpy.git.diff import parse_unified_diff
from harpy.git.snapshots import (
    MovingHeadError,
    SnapshotMeta,
    acquire_github_snapshot,
    canonical_diff,
    inventory_from_diff,
)
from harpy.git.source import read_git_blob, read_snapshot_path
from harpy.models import RevisionSnapshot
from harpy.proc import run


def _git(repo: Path, *args: str) -> None:
    result = run(["git", "-c", "commit.gpgsign=false", *args], cwd=repo, timeout=10)
    assert result.ok, result.stderr


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "src/app.py")
    _git(repo, "commit", "-m", "base")
    return repo


def test_canonical_diff_is_aggregate_not_per_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    base = run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=5).stdout.strip()
    (repo / "src" / "app.py").write_text("def old():\n    return 2\n", encoding="utf-8")
    _git(repo, "commit", "-am", "one")
    (repo / "src" / "app.py").write_text("def old():\n    return 3\n", encoding="utf-8")
    _git(repo, "commit", "-am", "two")
    head = run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=5).stdout.strip()
    raw = canonical_diff(repo, base, head)
    files = parse_unified_diff(raw)
    assert len(files) == 1
    patch = files[0].hunks[0].patch
    assert len(files[0].hunks) == 1
    assert "return 2" not in patch
    assert "return 1" in patch
    assert "return 3" in patch


def test_deleted_function_readable_at_base(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    base = run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=5).stdout.strip()
    (repo / "src" / "app.py").write_text("def newer():\n    return 0\n", encoding="utf-8")
    _git(repo, "commit", "-am", "delete old")
    read = read_git_blob(repo, base, "src/app.py", side="base")
    assert read.available
    assert "def old" in read.text


def test_rename_binary_and_mode_stay_visible() -> None:
    raw = """\
diff --git a/old.txt b/new.txt
similarity index 100%
rename from old.txt
rename to new.txt
diff --git a/data.bin b/data.bin
Binary files a/data.bin and b/data.bin differ
diff --git a/run.sh b/run.sh
old mode 100644
new mode 100755
diff --git a/vendor/lib b/vendor/lib
index 111 222 160000
--- a/vendor/lib
+++ b/vendor/lib
@@ -1 +1 @@
-Subproject commit aaa
+Subproject commit bbb
"""
    files = parse_unified_diff(raw)
    kinds = {item.path: item for item in files}
    assert kinds["new.txt"].status == "renamed"
    assert kinds["data.bin"].is_binary
    assert kinds["run.sh"].mode_change
    assert kinds["vendor/lib"].is_submodule
    inventory = {item.path: item.file_kind for item in inventory_from_diff(raw)}
    assert inventory["new.txt"] == "rename"
    assert inventory["data.bin"] == "binary"
    assert inventory["run.sh"] == "mode"
    assert inventory["vendor/lib"] == "submodule"


def test_moving_head_retries_once_then_fails() -> None:
    heads = ["a", "b", "c"]

    def fetch() -> SnapshotMeta:
        sha = heads.pop(0)
        return SnapshotMeta(base_tip_sha="base", comparison_base_sha="mb", head_sha=sha)

    calls = {"n": 0}

    def capture_meta(meta: SnapshotMeta) -> RevisionSnapshot:
        from datetime import UTC, datetime
        from hashlib import sha256
        from uuid import uuid4

        from harpy.models import RevisionSnapshot

        calls["n"] += 1
        return RevisionSnapshot(
            id=uuid4(),
            target_id=meta.target_id,
            base_tip_sha=meta.base_tip_sha,
            comparison_base_sha=meta.comparison_base_sha,
            head_sha=meta.head_sha,
            diff_digest=sha256(meta.head_sha.encode()).hexdigest(),
            created_at=datetime.now(UTC),
        )

    try:
        acquire_github_snapshot(fetch, capture_meta)
        raised = False
    except MovingHeadError:
        raised = True
    assert raised
    assert calls["n"] == 2


def test_path_escape_and_symlink_rejected(tmp_path: Path) -> None:
    root = tmp_path / "snap"
    root.mkdir()
    (root / "ok.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "secret"
    outside.write_text("password", encoding="utf-8")
    (root / "link").symlink_to(outside)
    escaped = read_snapshot_path(root, "../secret")
    assert not escaped.available
    linked = read_snapshot_path(root, "link")
    assert not linked.available
    assert linked.is_symlink or "symlink" in linked.reason
    ok = read_snapshot_path(root, "ok.py")
    assert ok.available
    assert ok.text.startswith("x")


def test_service_source_uses_snapshot_root(config: HarpyConfig, tmp_path: Path) -> None:
    root = tmp_path / "snap"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("ok\n", encoding="utf-8")
    read = ReviewService(config).get_source("src/a.py", root=root)
    assert read.available
    denied = ReviewService(config).get_source("../a.py", root=root)
    assert not denied.available
