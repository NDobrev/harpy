from __future__ import annotations

from pathlib import Path

from harpy.models import ScopePreset, ScopeSelection
from harpy.prefs import PrefsStore, config_dir
from harpy.review_scope import BUILTIN_PRESETS, default_selection


def test_config_dir_honours_xdg_and_explicit_root(tmp_path: Path) -> None:
    assert config_dir(root=tmp_path / "prefs") == tmp_path / "prefs"
    assert config_dir(env={"XDG_CONFIG_HOME": str(tmp_path / "xdg")}) == tmp_path / "xdg" / "harpy"


def test_selection_roundtrip(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    selection = default_selection()
    selection.enabled["tests"] = False
    selection.models["api"] = "gpt-5.6-sol-high"
    store.save_selection(selection)
    loaded = store.load_selection()
    assert loaded.enabled["tests"] is False
    assert loaded.models["api"] == "gpt-5.6-sol-high"


def test_corrupt_selection_falls_back_to_default(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    (tmp_path / "scope.json").write_text("{not json", encoding="utf-8")
    loaded = store.load_selection()
    assert loaded == default_selection()


def test_preset_create_and_delete(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    selection = default_selection()
    preset = ScopePreset(
        name="Auth-heavy",
        enabled=dict(selection.enabled),
        models=dict(selection.models),
    )
    assert store.save_preset(preset) is True
    names = {item.name for item in store.all_presets()}
    assert "Auth-heavy" in names
    assert store.delete_preset("Auth-heavy") is True
    assert "Auth-heavy" not in {item.name for item in store.user_presets()}


def test_builtin_presets_cannot_be_deleted_or_overwritten(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    builtin = BUILTIN_PRESETS[0]
    assert store.delete_preset(builtin.name) is False
    clone = ScopePreset(
        name=builtin.name,
        enabled=dict(builtin.enabled),
        models=dict(builtin.models),
    )
    assert store.save_preset(clone) is False
    assert store.user_presets() == []
    assert {item.name for item in store.all_presets()} >= {item.name for item in BUILTIN_PRESETS}


def test_corrupt_presets_are_empty(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    (tmp_path / "presets.json").write_text("[]not", encoding="utf-8")
    assert store.user_presets() == []


def test_disabled_repos_roundtrip(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    assert store.load_disabled_repos() == set()
    store.save_disabled_repos({"acme/pay", "acme/web"})
    assert store.load_disabled_repos() == {"acme/pay", "acme/web"}


def test_corrupt_disabled_repos_are_empty(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path)
    (tmp_path / "disabled_repos.json").write_text("{not a list", encoding="utf-8")
    assert store.load_disabled_repos() == set()


def test_missing_files_use_defaults(tmp_path: Path) -> None:
    store = PrefsStore(tmp_path / "missing")
    assert store.load_selection() == default_selection()
    assert store.user_presets() == []
    assert isinstance(store.load_selection(), ScopeSelection)
