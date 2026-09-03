from __future__ import annotations

from pathlib import Path

import pytest

from harpy.config import DEFAULT_MODEL, SELECTABLE_MODELS, HarpyConfig, SemanticConfig
from harpy.models import AnalysisResult, LogicalChange, PullRequest, ScopeSelection, ScoringWeights
from harpy.prefs import PrefsStore
from harpy.review_scope import default_selection
from harpy.tui.app import HarpyApp
from harpy.tui.screens.scope_dialog import ScopeDialog


def _enabled(tmp_path: Path) -> HarpyConfig:
    return HarpyConfig(
        semantic=SemanticConfig(
            model=DEFAULT_MODEL,
            enabled=True,
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


def _result(*, pending: bool = True, available: bool = False) -> AnalysisResult:
    return AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="abc",
            additions=1,
            deletions=0,
        ),
        changes=[LogicalChange(id="C1", title="auth")],
        pending_semantic=pending,
        semantic_available=available,
    )


@pytest.mark.asyncio
async def test_scope_dialog_does_not_auto_start(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path / "prefs")
    app = HarpyApp(_result(), config=_enabled(tmp_path), prefs=store)
    async with app.run_test() as pilot:
        assert app._semantic_running is False
        status = str(app.query_one("#status").render())
        assert "not started" in status
        await pilot.press("s")
        assert isinstance(app.screen, ScopeDialog)
        await pilot.press("escape")
        assert not isinstance(app.screen, ScopeDialog)
        assert app._semantic_running is False


@pytest.mark.asyncio
async def test_scope_dialog_enter_dismisses_with_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = PrefsStore(tmp_path / "prefs")
    captured: list[object] = []

    def fake_apply(result: object, **kwargs: object) -> object:
        captured.append(kwargs)
        return result

    monkeypatch.setattr("harpy.analysis.pipeline.apply_semantic", fake_apply)
    app = HarpyApp(_result(), config=_enabled(tmp_path), prefs=store)
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.press("enter")
        await pilot.pause()
    assert store.load_selection().enabled["changes"] is True
    assert captured
    kwargs = captured[0]
    assert isinstance(kwargs, dict)
    assert kwargs.get("force") is True
    assert kwargs.get("plan") is not None


@pytest.mark.asyncio
async def test_no_ai_scope_binding_is_inert(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path / "prefs")
    config = _enabled(tmp_path)
    app = HarpyApp(_result(pending=False), config=config, prefs=store)
    async with app.run_test() as pilot:
        await pilot.press("s")
        assert not isinstance(app.screen, ScopeDialog)


@pytest.mark.asyncio
async def test_dialog_returns_default_selection(tmp_path: Path) -> None:
    picked: list[ScopeSelection | None] = []
    app = HarpyApp(_result(), config=_enabled(tmp_path), prefs=PrefsStore(tmp_path / "prefs"))
    async with app.run_test() as pilot:
        await app.push_screen(
            ScopeDialog(
                default_selection(),
                models=SELECTABLE_MODELS,
                default_model=DEFAULT_MODEL,
            ),
            picked.append,
        )
        await pilot.press("enter")
        await pilot.pause()
    assert picked
    selection = picked[0]
    assert selection is not None
    assert selection.enabled["changes"] is True
