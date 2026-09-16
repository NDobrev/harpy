from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from harpy.analysis.capture import CapturedBlob, CaptureLimits, InboxHit, InboxHits
from harpy.analysis.opening import OpenQueued, OpenSpec, TenantReviewService
from harpy.config import HarpyConfig, SemanticConfig
from harpy.git.local import LocalSpec
from harpy.models import PullRequest, ScoringWeights
from harpy.proc import run
from harpy.storage.engine import create_sqlite_engine, initialize_engine
from harpy.storage.schema import LogicalChange, ReportChange, Review
from harpy.storage.workspace import ActorContext, TenantWorkspace, create_local_graph


def _engine(tmp_path: Path) -> Engine:
    engine = create_sqlite_engine(tmp_path / "harpy.sqlite3")
    initialize_engine(engine)
    return engine


def _session(engine: Engine) -> Session:
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)()


def _config(tmp_path: Path) -> HarpyConfig:
    return HarpyConfig(
        semantic=SemanticConfig(
            model="cursor-grok-4.6-high-fast",
            enabled=False,
            model_source="default",
            timeout_seconds=5,
        ),
        scoring=ScoringWeights(),
        generated_globs=(),
        high_impact=(),
        low_impact=(),
        cache_dir=tmp_path / "cache",
        path=None,
    )


def _git(repo: Path, *args: str) -> None:
    result = run(["git", "-c", "commit.gpgsign=false", *args], cwd=repo, timeout=10)
    assert result.ok, result.stderr


def _init_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "src/app.py")
    _git(repo, "commit", "-m", "base")
    _git(repo, "branch", "-M", "main")
    return repo


class FakeGithub:
    def __init__(self, repository_id: UUID) -> None:
        self.login = "octocat"
        self.semantic_calls = 0
        self.clone_calls = 0
        self.pr_calls = 0
        self.diff_calls = 0
        self.head = "a" * 40
        self.base = "b" * 40
        self.title = "Charge retry"
        self.body = "Retry failed charges"
        self.diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def old():\n"
            "-    return 1\n"
            "+    return 2\n"
        )
        self.blobs: dict[tuple[str, str], CapturedBlob] = {
            (self.base, "src/app.py"): CapturedBlob(True, data=b"def old():\n    return 1\n"),
            (self.head, "src/app.py"): CapturedBlob(True, data=b"def old():\n    return 2\n"),
        }
        self.inbox = InboxHits(
            [
                InboxHit(
                    number=12,
                    title="My review",
                    author="octocat",
                    repo="acme/pay",
                    repository_id=repository_id,
                )
            ]
        )
        self.fail_inbox = False

    def get_pr(self, number: int, *, repo: str) -> PullRequest:
        self.pr_calls += 1
        return PullRequest(
            number=number,
            title=self.title,
            body=self.body,
            base_ref="main",
            head_ref="topic",
            head_sha=self.head,
            base_sha=self.base,
            additions=1,
            deletions=1,
            repo=repo,
            state="open",
        )

    def get_diff(self, number: int, *, repo: str) -> str:
        del number, repo
        self.diff_calls += 1
        return self.diff

    def get_blob(self, sha: str, path: str) -> CapturedBlob:
        return self.blobs.get((sha, path), CapturedBlob(False, reason="missing_snapshot"))

    def search_prs(self, tab: str, *, open_only: bool, login: str) -> InboxHits:
        del tab, open_only
        if login != self.login:
            raise RuntimeError("service account")
        if self.fail_inbox:
            raise RuntimeError("rate limited")
        return self.inbox


def _service(
    session: Session,
    context: ActorContext,
    tmp_path: Path,
    github: FakeGithub | None = None,
    limits: CaptureLimits | None = None,
) -> TenantReviewService:
    return TenantReviewService(
        session,
        context,
        artifact_root=tmp_path / "artifacts",
        config=_config(tmp_path),
        github=github,
        limits=limits,
    )


def _open_and_run(service: TenantReviewService, spec: OpenSpec) -> tuple[UUID, UUID]:
    opened = service.open_target(spec, idempotency_key=uuid4())
    assert isinstance(opened, OpenQueued)
    job = service.run_job(opened.job_id)
    assert job.status == "completed", job.error
    assert job.result_report_id is not None
    return opened.review_id, job.result_report_id


def test_at_001_open_saved_report_does_not_acquire(tmp_path: Path) -> None:
    session = _session(_engine(tmp_path))
    context, review_id, report_id, _change = create_local_graph(session, slug="local")
    review = session.get(Review, (context.tenant_id, review_id))
    assert review is not None
    github = FakeGithub(review.repository_id)
    service = _service(session, context, tmp_path, github)
    opened = service.open_target(
        OpenSpec(repository_id=review.repository_id, kind="github_pr", pr_number=482),
        idempotency_key=uuid4(),
    )
    assert opened.state == "ready"
    assert opened.report_id == report_id
    viewed = service.get_report(review_id, report_id)
    assert viewed.report_id == report_id
    assert github.pr_calls == 0
    assert github.diff_calls == 0
    assert github.clone_calls == 0
    assert github.semantic_calls == 0
    assert service.semantic_calls == 0


def test_at_002_open_new_github_pr_is_static_only(tmp_path: Path) -> None:
    session = _session(_engine(tmp_path))
    context, _review_id, _report_id, _change = create_local_graph(session, slug="acq")
    workspace = TenantWorkspace(session, context, artifact_root=tmp_path / "artifacts")
    repository = workspace.add_repository(
        provider="github",
        host="github.com",
        display_name="acme/pay",
        provider_repository_id="77",
    )
    credential = workspace.put_credential(kind="github", ciphertext="c", nonce="n", key_id="k1")
    credential.verified_login = "octocat"
    github = FakeGithub(repository.id)
    service = _service(session, context, tmp_path, github)
    _review_id, report_id = _open_and_run(
        service,
        OpenSpec(repository_id=repository.id, kind="github_pr", pr_number=9),
    )
    opened = service.open_target(
        OpenSpec(repository_id=repository.id, kind="github_pr", pr_number=9),
        idempotency_key=uuid4(),
    )
    assert opened.state == "ready"
    assert opened.report_id == report_id
    report = service.get_report(opened.review_id, report_id)
    assert report.kind == "static"
    assert report.change_count >= 1
    assert github.clone_calls == 0
    assert github.semantic_calls == 0
    assert service.semantic_calls == 0
    again = service.open_target(
        OpenSpec(repository_id=repository.id, kind="github_pr", pr_number=9),
        idempotency_key=uuid4(),
    )
    assert again.state == "ready"
    assert github.pr_calls == 3


def test_at_003_inbox_refresh_uses_personal_identity(tmp_path: Path) -> None:
    session = _session(_engine(tmp_path))
    context, _review_id, _report_id, _change = create_local_graph(session, slug="inbox")
    workspace = TenantWorkspace(session, context, artifact_root=tmp_path / "artifacts")
    repository = workspace.add_repository(
        provider="github",
        host="github.com",
        display_name="acme/pay",
        provider_repository_id="88",
    )
    credential = workspace.put_credential(kind="github", ciphertext="c", nonce="n", key_id="k1")
    credential.verified_login = "octocat"
    github = FakeGithub(repository.id)
    service = _service(session, context, tmp_path, github)
    first = service.inbox("authored", idempotency_key=uuid4())
    assert first.job_id is not None
    assert first.rows == []
    service.run_job(first.job_id)
    cached = service.list_inbox("authored")
    assert cached.login == "octocat"
    assert cached.rows[0].author == "octocat"
    assert cached.rows[0].title == "My review"
    assert github.clone_calls == 0
    assert service.semantic_calls == 0
    fetched = cached.fetched_at
    github.fail_inbox = True
    job_id = service.refresh_inbox("authored", idempotency_key=uuid4())
    failed = service.run_job(job_id)
    assert failed.status == "failed"
    retained = service.list_inbox("authored")
    assert retained.rows[0].title == "My review"
    assert retained.error == "rate limited"
    assert retained.fetched_at == fetched


def test_at_005_local_comparison_matrix(tmp_path: Path) -> None:
    session = _session(_engine(tmp_path))
    context, _review_id, _report_id, _change = create_local_graph(session, slug="localcmp")
    repo = _init_repo(tmp_path)
    _git(repo, "checkout", "-b", "topic")
    (repo / "src" / "app.py").write_text("def old():\n    return 9\n", encoding="utf-8")
    _git(repo, "commit", "-am", "topic")
    (repo / "src" / "app.py").write_text("def old():\n    return 8\n", encoding="utf-8")
    _git(repo, "add", "src/app.py")
    (repo / "src" / "app.py").write_text("def old():\n    return 7\n", encoding="utf-8")
    (repo / "src" / "extra.py").write_text("VALUE = 1\n", encoding="utf-8")
    head_before = run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=5).stdout.strip()
    index_before = run(["git", "ls-files", "--stage"], cwd=repo, timeout=5).stdout
    status_before = run(["git", "status", "--porcelain"], cwd=repo, timeout=5).stdout
    service = _service(session, context, tmp_path)
    repository_id = service.register_local_repository(repo)

    _committed_review, committed = _open_and_run(
        service,
        OpenSpec(
            repository_id=repository_id,
            kind="local_committed",
            base_ref="main",
        ),
    )
    _staged_review, staged = _open_and_run(
        service,
        OpenSpec(repository_id=repository_id, kind="local_staged"),
    )
    _working_review, working = _open_and_run(
        service,
        OpenSpec(
            repository_id=repository_id,
            kind="local_working_tree",
            include_untracked=False,
        ),
    )
    _untracked_review, untracked = _open_and_run(
        service,
        OpenSpec(
            repository_id=repository_id,
            kind="local_working_tree",
            include_untracked=True,
        ),
    )
    committed_files = {row.path for row in service.snapshot_files(committed)}
    staged_files = {row.path for row in service.snapshot_files(staged)}
    working_files = {row.path for row in service.snapshot_files(working)}
    untracked_files = {row.path for row in service.snapshot_files(untracked)}
    assert committed_files == {"src/app.py"}
    assert staged_files == {"src/app.py"}
    assert working_files == {"src/app.py"}
    assert "src/extra.py" in untracked_files
    assert "src/extra.py" not in working_files
    extra = next(row.id for row in service.snapshot_files(untracked) if row.path == "src/extra.py")
    source = service.get_source(untracked, extra, side="head")
    assert source.available
    assert any("VALUE = 1" in line.text for line in source.lines)
    assert run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=5).stdout.strip() == head_before
    assert run(["git", "ls-files", "--stage"], cwd=repo, timeout=5).stdout == index_before
    assert run(["git", "status", "--porcelain"], cwd=repo, timeout=5).stdout == status_before

    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init")
    empty_id = service.register_local_repository(empty)
    opened = service.open_target(
        OpenSpec(repository_id=empty_id, kind="local_committed", base_ref="HEAD"),
        idempotency_key=uuid4(),
    )
    assert isinstance(opened, OpenQueued)
    job = service.run_job(opened.job_id)
    assert job.status == "failed"
    assert job.error is not None
    assert job.error["code"] == "unsupported_comparison"

    other = _init_repo(tmp_path, "conflict")
    _git(other, "checkout", "-b", "other")
    (other / "src" / "app.py").write_text("def old():\n    return 3\n", encoding="utf-8")
    _git(other, "commit", "-am", "other")
    _git(other, "checkout", "main")
    (other / "src" / "app.py").write_text("def old():\n    return 4\n", encoding="utf-8")
    _git(other, "commit", "-am", "mainline")
    run(["git", "merge", "other"], cwd=other, timeout=10)
    conflict_id = service.register_local_repository(other)
    conflict_open = service.open_target(
        OpenSpec(repository_id=conflict_id, kind="local_staged"),
        idempotency_key=uuid4(),
    )
    assert isinstance(conflict_open, OpenQueued)
    conflict_job = service.run_job(conflict_open.job_id)
    assert conflict_job.status == "failed"
    assert conflict_job.error is not None
    assert conflict_job.error["code"] == "unsupported_comparison"


def test_at_006_capture_race_retries_then_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(_engine(tmp_path))
    context, _review_id, _report_id, _change = create_local_graph(session, slug="race")
    repo = _init_repo(tmp_path, "moving")
    (repo / "src" / "app.py").write_text("def old():\n    return 4\n", encoding="utf-8")
    service = _service(session, context, tmp_path)
    repository_id = service.register_local_repository(repo)
    sequence = iter(["one", "two", "two", "two"])

    def once(repo_path: Path, spec: LocalSpec) -> str:
        del repo_path, spec
        return next(sequence)

    monkeypatch.setattr("harpy.git.local.worktree_fingerprint", once)
    review_id, report_id = _open_and_run(
        service,
        OpenSpec(
            repository_id=repository_id,
            kind="local_working_tree",
            include_untracked=False,
        ),
    )
    assert service.get_report(review_id, report_id).kind == "static"

    calls = {"n": 0}

    def always_moving(repo_path: Path, spec: LocalSpec) -> str:
        del repo_path, spec
        calls["n"] += 1
        return str(calls["n"])

    monkeypatch.setattr("harpy.git.local.worktree_fingerprint", always_moving)
    opened = service.open_target(
        OpenSpec(
            repository_id=repository_id,
            kind="local_working_tree",
            include_untracked=True,
        ),
        idempotency_key=uuid4(),
    )
    assert isinstance(opened, OpenQueued)
    job = service.run_job(opened.job_id)
    assert job.status == "failed"
    assert job.error is not None
    assert job.error["code"] == "repository_changed"
    assert job.result_report_id is None


def test_at_007_diff_ownership_and_original_patch(tmp_path: Path) -> None:
    session = _session(_engine(tmp_path))
    context, _review_id, _report_id, _change = create_local_graph(session, slug="diff")
    repo = _init_repo(tmp_path, "owned")
    (repo / "src" / "new.py").write_text("print(1)\n", encoding="utf-8")
    (repo / "src" / "gone.py").write_text("gone\n", encoding="utf-8")
    _git(repo, "add", "src/new.py", "src/gone.py")
    _git(repo, "commit", "-m", "add files")
    _git(repo, "mv", "src/new.py", "src/renamed.py")
    (repo / "src" / "gone.py").unlink()
    (repo / "src" / "app.py").write_text("def old():\n    return 5\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "mixed")
    service = _service(session, context, tmp_path)
    repository_id = service.register_local_repository(repo)
    review_id, report_id = _open_and_run(
        service,
        OpenSpec(repository_id=repository_id, kind="local_committed", base_ref="HEAD~1"),
    )
    review = service.workspace.get_review(review_id)
    files = {row.path: row for row in service.snapshot_files(report_id)}
    assert "src/renamed.py" in files
    assert files["src/renamed.py"].old_path == "src/new.py"
    assert files["src/gone.py"].head_available is False
    assert files["src/gone.py"].availability_reason == "absent_side"
    assert files["src/renamed.py"].head_available is True
    added = service.get_source(report_id, files["src/renamed.py"].id, side="head")
    deleted = service.get_source(report_id, files["src/gone.py"].id, side="base")
    assert added.available
    assert deleted.available
    app = service.get_diff(report_id, files["src/app.py"].id)
    assert app.patch is not None
    assert "return 1" in app.patch or "return 5" in app.patch
    assert any(row.owner_change_ids for row in app.rows)
    patch_view = service.get_diff(report_id, files["src/app.py"].id, mode="patch")
    assert any(row.text.startswith("diff --git") for row in patch_view.rows)
    first = service.list_changes(report_id)[0]
    extra_id = uuid4()
    session.add(
        LogicalChange(
            tenant_id=context.tenant_id,
            review_id=review.id,
            id=extra_id,
            lineage={},
        )
    )
    session.flush()
    session.add(
        ReportChange(
            tenant_id=context.tenant_id,
            report_id=report_id,
            change_id=extra_id,
            review_id=review.id,
            local_id="C-SHARE",
            rank_index=99,
            projection={"paths": first.paths, "hunk_ids": first.hunk_ids, "title": "shared"},
        )
    )
    session.flush()
    shared = service.get_diff(report_id, files["src/app.py"].id)
    owners = next(row.owner_change_ids for row in shared.rows if row.owner_change_ids)
    assert first.change_id in owners
    assert extra_id in owners


def test_at_008_source_unavailable_states(tmp_path: Path) -> None:
    session = _session(_engine(tmp_path))
    context, _review_id, _report_id, _change = create_local_graph(session, slug="src")
    workspace = TenantWorkspace(session, context, artifact_root=tmp_path / "artifacts")
    repository = workspace.add_repository(
        provider="github",
        host="github.com",
        display_name="acme/pay",
        provider_repository_id="55",
    )
    credential = workspace.put_credential(kind="github", ciphertext="c", nonce="n", key_id="k1")
    credential.verified_login = "octocat"
    github = FakeGithub(repository.id)
    github.diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
 def old():
-    return 1
+    return 2
diff --git a/data.bin b/data.bin
Binary files a/data.bin and b/data.bin differ
diff --git a/link b/link
new file mode 120000
--- /dev/null
+++ b/link
@@ -0,0 +1 @@
+outside
diff --git a/vendor/lib b/vendor/lib
index 111 222 160000
--- a/vendor/lib
+++ b/vendor/lib
@@ -1 +1 @@
-Subproject commit 111
+Subproject commit 222
diff --git a/odd.txt b/odd.txt
--- a/odd.txt
+++ b/odd.txt
@@ -1 +1 @@
-old
+new
diff --git a/huge.txt b/huge.txt
--- /dev/null
+++ b/huge.txt
@@ -0,0 +1 @@
+xxxx
diff --git a/missing.py b/missing.py
--- /dev/null
+++ b/missing.py
@@ -0,0 +1 @@
+absent
"""
    github.blobs = {
        (github.base, "src/app.py"): CapturedBlob(True, data=b"def old():\n    return 1\n"),
        (github.head, "src/app.py"): CapturedBlob(True, data=b"def old():\n    return 2\n"),
        (github.head, "data.bin"): CapturedBlob(True, data=b"\x00\x01"),
        (github.head, "link"): CapturedBlob(False, reason="symlink", symlink=True),
        (github.head, "vendor/lib"): CapturedBlob(False, reason="submodule", submodule=True),
        (github.head, "odd.txt"): CapturedBlob(True, data=b"\xff\xfe"),
        (github.head, "huge.txt"): CapturedBlob(True, data=b"x" * 80),
        (github.head, "missing.py"): CapturedBlob(False, reason="missing_snapshot"),
    }
    service = _service(session, context, tmp_path, github, limits=CaptureLimits(max_text_file=16))
    _review_id, report_id = _open_and_run(
        service, OpenSpec(repository_id=repository.id, kind="github_pr", pr_number=3)
    )
    files = {row.path: row for row in service.snapshot_files(report_id)}
    assert files["data.bin"].availability_reason == "binary"
    assert files["link"].availability_reason == "symlink"
    assert files["vendor/lib"].availability_reason == "submodule"
    assert files["odd.txt"].availability_reason == "unsupported_encoding"
    assert files["huge.txt"].availability_reason == "size_limit"
    assert files["missing.py"].availability_reason == "missing_snapshot"
    source = service.get_source(report_id, files["data.bin"].id, side="head")
    assert source.available is False
    assert source.host_path is None
    assert source.reason == "binary"
    github.diff = (
        "diff --git a/../secret b/../secret\n--- /dev/null\n+++ b/../secret\n@@ -0,0 +1 @@\n+nope\n"
    )
    opened = service.open_target(
        OpenSpec(repository_id=repository.id, kind="github_pr", pr_number=3, acquire_latest=True),
        idempotency_key=uuid4(),
    )
    assert isinstance(opened, OpenQueued)
    job = service.run_job(opened.job_id)
    assert job.status == "failed"


def test_at_020_freshness_keeps_selected_report(tmp_path: Path) -> None:
    session = _session(_engine(tmp_path))
    context, _review_id, _report_id, _change = create_local_graph(session, slug="fresh")
    workspace = TenantWorkspace(session, context, artifact_root=tmp_path / "artifacts")
    repository = workspace.add_repository(
        provider="github",
        host="github.com",
        display_name="acme/pay",
        provider_repository_id="33",
    )
    credential = workspace.put_credential(kind="github", ciphertext="c", nonce="n", key_id="k1")
    credential.verified_login = "octocat"
    github = FakeGithub(repository.id)
    service = _service(session, context, tmp_path, github)
    _review_id, first_id = _open_and_run(
        service, OpenSpec(repository_id=repository.id, kind="github_pr", pr_number=4)
    )
    first_open = service.open_target(
        OpenSpec(repository_id=repository.id, kind="github_pr", pr_number=4),
        idempotency_key=uuid4(),
    )
    assert first_open.state == "ready"
    first_change = service.list_changes(first_id)[0]
    workspace.set_decision(
        report_id=first_id,
        change_id=first_change.change_id,
        status="reviewed",
        expected_version=0,
        idempotency_key=uuid4(),
    )
    old_source = service.get_source(first_id, service.snapshot_files(first_id)[0].id, side="head")
    github.head = "c" * 40
    github.blobs[(github.head, "src/app.py")] = CapturedBlob(
        True, data=b"def old():\n    return 9\n"
    )
    github.diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def old():\n"
        "-    return 1\n"
        "+    return 9\n"
    )
    _second_review, second_id = _open_and_run(
        service,
        OpenSpec(
            repository_id=repository.id,
            kind="github_pr",
            pr_number=4,
            acquire_latest=True,
        ),
    )
    assert second_id != first_id
    still = service.get_report(first_open.review_id, first_id)
    latest = service.get_report(first_open.review_id, second_id)
    assert still.report_id == first_id
    assert still.freshness == "code_changed"
    assert latest.freshness == "current"
    assert still.analyzed_revision == "a" * 40
    assert latest.analyzed_revision == "c" * 40
    reread = service.get_source(first_id, service.snapshot_files(first_id)[0].id, side="head")
    assert [line.text for line in reread.lines] == [line.text for line in old_source.lines]
    assert service.list_changes(first_id)[0].status == "reviewed"
    assert service.list_changes(second_id)[0].status == "unreviewed"
    review = service.workspace.get_review(first_open.review_id)
    review.last_observation = {"observed_at": "2026-09-16T00:00:00+00:00"}
    session.flush()
    unknown = service.get_report(first_open.review_id, first_id)
    assert unknown.freshness == "unknown"
