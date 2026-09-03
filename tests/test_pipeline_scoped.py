from __future__ import annotations

from pathlib import Path

from harpy.analysis.pipeline import analyze_static, apply_semantic
from harpy.cache.store import CacheStore, cache_key
from harpy.config import DEFAULT_MODEL, HarpyConfig, SemanticConfig
from harpy.models import (
    ApiEndpointImpact,
    ChangeAnnotation,
    SemanticAnalysisResult,
    SemanticChangeDraft,
)
from harpy.review_scope import default_selection, plan_calls, signature


class _ScopedSemantic:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        assert workspace.is_dir()
        self.prompts.append(prompt)
        if '"annotations"' in prompt and '"changes"' not in prompt:
            return SemanticAnalysisResult(
                annotations=[
                    ChangeAnnotation(
                        change_id="C1", security_sensitivity=8, review_questions=["ok?"]
                    )
                ]
            )
        if '"api_impacts"' in prompt and '"changes"' not in prompt:
            return SemanticAnalysisResult(
                api_impacts=[
                    ApiEndpointImpact(
                        change_id="C1",
                        method="DELETE",
                        path="/users",
                        summary="org admin delete",
                    )
                ]
            )
        return SemanticAnalysisResult(
            pr_intent="org admins",
            changes=[
                SemanticChangeDraft(
                    id="C1",
                    title="org admin delete",
                    hunk_ids=["H1"],
                    files=["src/auth/permissions.py"],
                    risk="high",
                )
            ],
        )


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


def test_multi_call_plan_merges_and_uses_known_changes(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    enabled = _enabled(config, tmp_path / "cache-scoped")
    draft = analyze_static("1842", config=enabled, use_ai=True, use_cache=False)
    selection = default_selection()
    selection.models["security"] = "gpt-5.6-sol-high"
    selection.models["questions"] = "gpt-5.6-sol-high"
    selection.enabled["api"] = False
    selection.enabled["db"] = False
    selection.enabled["diagrams"] = False
    selection.enabled["tests"] = False
    selection.enabled["omissions"] = False
    calls = plan_calls(selection)
    assert len(calls) == 2
    semantic = _ScopedSemantic()
    result = apply_semantic(
        draft,
        config=enabled,
        semantic_client=semantic,
        use_cache=False,
        plan=calls,
        scope_signature=signature(selection),
    )
    assert result.semantic_available
    assert result.changes[0].title == "org admin delete"
    assert result.changes[0].security_sensitivity == 8
    assert result.changes[0].review_questions == ["ok?"]
    assert any("KNOWN CHANGES" in prompt for prompt in semantic.prompts)
    assert len(semantic.prompts) == 2


def test_scope_signature_changes_cache_key() -> None:
    base = dict(repo="r", base_sha="a", head_sha="b", model=DEFAULT_MODEL)
    assert cache_key(**base) == cache_key(**base, scope_signature="")
    assert cache_key(**base, scope_signature="api:x") != cache_key(**base)


def test_force_reruns_after_complete(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    enabled = _enabled(config, tmp_path / "cache-force")
    draft = analyze_static("1842", config=enabled, use_ai=True, use_cache=True)
    semantic = _ScopedSemantic()
    first = apply_semantic(draft, config=enabled, semantic_client=semantic, use_cache=True)
    assert first.semantic_available
    assert not first.pending_semantic
    assert semantic.prompts
    count = len(semantic.prompts)
    again = apply_semantic(
        first, config=enabled, semantic_client=semantic, use_cache=True, force=True
    )
    assert again.semantic_available
    assert len(semantic.prompts) == count + 1
    assert CacheStore(enabled.cache_dir).get(again.analysis_key) is not None
