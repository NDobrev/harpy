from __future__ import annotations

from pathlib import Path

from harpy.analysis.pipeline import analyze
from harpy.cache.store import CacheStore, cache_key
from harpy.config import HarpyConfig, SemanticConfig
from harpy.github.gh import GhProvider
from harpy.models import PullRequest, SemanticAnalysisResult, SemanticChangeDraft


def test_static_pipeline(config: HarpyConfig, fake_gh_path: Path) -> None:
    result = analyze("1842", config=config, use_ai=False, use_cache=False)
    assert result.files
    assert result.hunks
    assert result.changes
    assert result.changes[0].files


class _FakeSemantic:
    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        assert prompt
        assert workspace.is_dir()
        return SemanticAnalysisResult(
            pr_intent="org admins",
            changes=[
                SemanticChangeDraft(
                    id="C1",
                    title="org admin delete",
                    before="project admins only",
                    after="org admins too",
                    why="new privilege",
                    affected_components=["DELETE /users"],
                    review_questions=["owners?"],
                    possible_omissions=["no audit"],
                    hunk_ids=["H1"],
                    files=["src/auth/permissions.py"],
                    risk="high",
                    confidence=0.9,
                    unexpectedness=0.1,
                    behavior_change=8,
                    business_impact=8,
                )
            ],
        )


def test_semantic_fills_context_without_worktree(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    enabled = HarpyConfig(
        semantic=SemanticConfig(
            model=config.semantic.model,
            enabled=True,
            model_source="default",
            timeout_seconds=5,
        ),
        scoring=config.scoring,
        generated_globs=(),
        high_impact=(),
        low_impact=(),
        cache_dir=tmp_path / "cache",
        path=None,
    )
    result = analyze(
        "1842",
        config=enabled,
        use_ai=True,
        use_cache=True,
        semantic_client=_FakeSemantic(),
    )
    change = result.changes[0]
    assert change.before == "project admins only"
    assert change.affected_components == ["DELETE /users"]
    assert change.review_questions == ["owners?"]
    assert result.semantic_available
    key = cache_key(
        repo=result.pr.repo or "acme/app",
        base_sha=result.pr.base_sha or result.pr.base_ref,
        head_sha=result.pr.head_sha,
        model=enabled.semantic.model,
    )
    assert CacheStore(enabled.cache_dir).get(key) is not None


def test_analyze_static_leaves_semantic_pending(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    from harpy.analysis.pipeline import analyze_static, apply_semantic

    enabled = HarpyConfig(
        semantic=SemanticConfig(
            model=config.semantic.model,
            enabled=True,
            model_source="default",
            timeout_seconds=5,
        ),
        scoring=config.scoring,
        generated_globs=(),
        high_impact=(),
        low_impact=(),
        cache_dir=tmp_path / "cache-pending",
        path=None,
    )
    notes: list[str] = []
    draft = analyze_static(
        "1842",
        config=enabled,
        use_ai=True,
        use_cache=True,
        progress=notes.append,
    )
    assert draft.pending_semantic
    assert draft.workspace_path
    assert not draft.semantic_available
    assert CacheStore(enabled.cache_dir).get(draft.analysis_key) is None
    assert any("Static ranking ready" in note for note in notes)

    result = apply_semantic(draft, config=enabled, semantic_client=_FakeSemantic())
    assert not result.pending_semantic
    assert result.semantic_available
    assert result.changes[0].before == "project admins only"
    assert CacheStore(enabled.cache_dir).get(result.analysis_key) is not None


class _CountingGh(GhProvider):
    def __init__(self) -> None:
        super().__init__()
        self.pr_calls = 0
        self.diff_calls = 0

    def get_pr(self, number: int | None, *, repo: str | None = None) -> PullRequest:
        self.pr_calls += 1
        return super().get_pr(number, repo=repo)

    def get_diff(self, number: int | None, *, repo: str | None = None) -> str:
        self.diff_calls += 1
        return super().get_diff(number, repo=repo)


class _CountingSemantic:
    def __init__(self) -> None:
        self.calls = 0

    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        self.calls += 1
        return _FakeSemantic().analyze_text(prompt, workspace=workspace)


class _DegradedSemantic:
    def __init__(self) -> None:
        self.calls = 0

    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        self.calls += 1
        assert prompt
        assert workspace.is_dir()
        return SemanticAnalysisResult(degraded=True, error="agent failed")


def _enabled(config: HarpyConfig, cache_dir: Path) -> HarpyConfig:
    return HarpyConfig(
        semantic=SemanticConfig(
            model=config.semantic.model,
            enabled=True,
            model_source="default",
            timeout_seconds=5,
        ),
        scoring=config.scoring,
        generated_globs=(),
        high_impact=(),
        low_impact=(),
        cache_dir=cache_dir,
        path=None,
    )


def test_reopen_loads_cached_semantic_without_redoing_work(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    from harpy.analysis.pipeline import analyze_static, apply_semantic

    enabled = _enabled(config, tmp_path / "cache-reopen")
    provider = _CountingGh()
    semantic = _CountingSemantic()
    first = analyze_static(
        "1842",
        config=enabled,
        use_ai=True,
        use_cache=True,
        provider=provider,
    )
    assert first.pending_semantic
    apply_semantic(first, config=enabled, semantic_client=semantic)
    assert provider.diff_calls == 1
    assert semantic.calls == 1

    notes: list[str] = []
    second = analyze_static(
        "1842",
        config=enabled,
        use_ai=True,
        use_cache=True,
        provider=provider,
        progress=notes.append,
    )
    assert provider.pr_calls == 2
    assert provider.diff_calls == 1
    assert semantic.calls == 1
    assert second.semantic_available
    assert not second.pending_semantic
    assert second.changes[0].before == "project admins only"
    assert any("Loaded cached analysis" in note for note in notes)
    assert not any("Preparing checkout" in note for note in notes)
    assert not any("Scoring" in note for note in notes)


def test_degraded_semantic_is_cached_so_agent_is_not_recalled(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    from harpy.analysis.pipeline import analyze_static, apply_semantic

    enabled = _enabled(config, tmp_path / "cache-degraded")
    semantic = _DegradedSemantic()
    draft = analyze_static("1842", config=enabled, use_ai=True, use_cache=True)
    result = apply_semantic(draft, config=enabled, semantic_client=semantic)
    assert not result.pending_semantic
    assert not result.semantic_available
    assert CacheStore(enabled.cache_dir).get(result.analysis_key) is not None
    assert semantic.calls == 1

    second = analyze_static("1842", config=enabled, use_ai=True, use_cache=True)
    assert not second.pending_semantic
    assert not second.semantic_available
    assert semantic.calls == 1


def test_cache_write_failure_does_not_drop_semantic(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    from harpy.analysis.pipeline import analyze_static, apply_semantic

    enabled = _enabled(config, tmp_path / "cache-readonly")
    draft = analyze_static("1842", config=enabled, use_ai=True, use_cache=True)
    store_root = enabled.cache_dir / "analyses"
    store_root.mkdir(parents=True, exist_ok=True)
    store_root.chmod(0o555)
    try:
        result = apply_semantic(draft, config=enabled, semantic_client=_FakeSemantic())
    finally:
        store_root.chmod(0o755)
    assert result.semantic_available
    assert result.changes[0].before == "project admins only"
