from __future__ import annotations

from pathlib import Path

from harpy.config import DEFAULT_MODEL, SELECTABLE_MODELS, load_config, with_model
from harpy.models import ScopeSelection
from harpy.review_scope import (
    BUILTIN_PRESETS,
    SCOPES,
    apply_preset,
    default_selection,
    normalize,
    plan_calls,
    signature,
)


def test_selectable_models_start_with_default() -> None:
    assert SELECTABLE_MODELS[0] == DEFAULT_MODEL


def test_default_selection_enables_every_scope_on_grok() -> None:
    selection = default_selection()
    assert all(selection.enabled[item.id] for item in SCOPES)
    assert all(model == DEFAULT_MODEL for model in selection.models.values())
    assert selection.preset == "Everything"
    assert signature(selection) == ""


def test_diagrams_disabled_when_contracts_are_off() -> None:
    selection = default_selection()
    selection.enabled["api"] = False
    selection.enabled["db"] = False
    norm = normalize(selection)
    assert norm.enabled["diagrams"] is False


def test_plan_groups_by_model_and_stages_changes_first() -> None:
    other = "gpt-5.6-sol-high"
    selection = default_selection()
    selection.models["api"] = other
    selection.models["db"] = other
    calls = plan_calls(selection)
    assert len(calls) == 2
    first, second = calls
    assert first.stage == 0
    assert "changes" in first.scope_ids
    assert first.model == DEFAULT_MODEL
    assert second.stage == 1
    assert second.model == other
    assert "api" in second.scope_ids
    assert "db" in second.scope_ids
    assert "diagrams" in second.scope_ids
    assert first.context_name != second.context_name


def test_signature_is_stable_and_empty_for_default() -> None:
    other = default_selection()
    other.enabled["tests"] = False
    assert signature(other) == signature(other)
    assert signature(other) != ""
    assert "tests" not in signature(other)


def test_builtin_presets_exist() -> None:
    names = {item.name for item in BUILTIN_PRESETS}
    assert names == {"Everything", "Security", "API", "Database", "Fast triage"}
    fast = next(item for item in BUILTIN_PRESETS if item.name == "Fast triage")
    applied = apply_preset(fast)
    assert applied.enabled["changes"] is True
    assert applied.enabled["api"] is False
    assert applied.enabled["diagrams"] is False


def test_with_model_replaces_only_the_model(tmp_path: Path) -> None:
    config = load_config(start=tmp_path, env={})
    updated = with_model(config, "gpt-5.6-sol-high")
    assert updated.semantic.model == "gpt-5.6-sol-high"
    assert updated.semantic.model_source == "scope"
    assert config.semantic.model == DEFAULT_MODEL


def test_toml_can_override_selectable_models(tmp_path: Path) -> None:
    (tmp_path / ".harpy.toml").write_text(
        '[semantic]\nmodel = "cursor-grok-4.6-high-fast"\nmodels = ["alpha", "beta"]\n',
        encoding="utf-8",
    )
    loaded = load_config(start=tmp_path, env={})
    assert loaded.selectable_models == ("alpha", "beta")


def test_changes_deselected_makes_every_call_stage_one() -> None:
    selection = ScopeSelection(
        enabled={item.id: item.id in {"api", "diagrams"} for item in SCOPES},
        models={item.id: DEFAULT_MODEL for item in SCOPES if item.kind != "modifier"},
    )
    calls = plan_calls(selection)
    assert calls
    assert all(call.stage == 1 for call in calls)
    assert "api" in calls[0].scope_ids
    assert "diagrams" in calls[0].scope_ids
