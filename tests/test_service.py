from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from harpy.analysis.pipeline import analyze_static, apply_semantic
from harpy.analysis.service import ReviewService
from harpy.analysis.workflows.events import make_event, should_apply_event
from harpy.config import HarpyConfig, SemanticConfig
from harpy.models import (
    RunStatus,
    SemanticAnalysisResult,
    SemanticChangeDraft,
)


class _OkThenFail:
    def __init__(self) -> None:
        self.calls = 0

    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        self.calls += 1
        if '"changes"' in prompt:
            return SemanticAnalysisResult(
                pr_intent="keep",
                changes=[
                    SemanticChangeDraft(
                        id="C1", title="kept", hunk_ids=["H1"], files=["src/auth/permissions.py"]
                    )
                ],
            )
        return SemanticAnalysisResult(degraded=True, error="scope failed")


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


def test_apply_semantic_does_not_mutate_rendered_result(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    enabled = _enabled(config, tmp_path / "cache")
    rendered = analyze_static("1842", config=enabled, use_ai=True, use_cache=False)
    before = rendered.model_dump()
    apply_semantic(
        rendered,
        config=enabled,
        semantic_client=_OkThenFail(),
        force=True,
        use_cache=False,
    )
    assert rendered.model_dump() == before


def test_scope_failure_keeps_completed_changes(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    from harpy.review_scope import default_selection, plan_calls

    enabled = _enabled(config, tmp_path / "cache-partial")
    draft = analyze_static("1842", config=enabled, use_ai=True, use_cache=False)
    selection = default_selection()
    selection.models["security"] = "gpt-5.6-sol-high"
    plan = plan_calls(selection, default_model=enabled.semantic.model)
    updated = apply_semantic(
        draft,
        config=enabled,
        semantic_client=_OkThenFail(),
        plan=plan,
        force=True,
        use_cache=False,
    )
    assert updated.changes
    assert updated.changes[0].title == "kept"
    assert updated.banner is not None


def test_late_event_is_ignored() -> None:
    review_id = uuid4()
    run_id = uuid4()
    snapshot_id = uuid4()
    event = make_event(
        run_id=run_id,
        review_id=review_id,
        snapshot_id=snapshot_id,
        sequence=2,
        status=RunStatus.COMPLETED,
        message="done",
    )
    assert should_apply_event(event, review_id=review_id, run_id=run_id, min_sequence=1)
    assert not should_apply_event(event, review_id=uuid4(), run_id=run_id)
    assert not should_apply_event(event, review_id=review_id, run_id=uuid4())
    assert not should_apply_event(event, review_id=review_id, run_id=run_id, min_sequence=2)


def test_review_service_rejects_stale_run(config: HarpyConfig) -> None:
    service = ReviewService(config)
    review_id = uuid4()
    run_id = uuid4()
    event = make_event(
        run_id=run_id,
        review_id=review_id,
        snapshot_id=uuid4(),
        sequence=1,
        status=RunStatus.RUNNING,
    )
    assert service.accept_event(event, review_id=review_id, run_id=run_id)
    assert not service.accept_event(event, review_id=review_id, run_id=uuid4())
