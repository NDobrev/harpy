from __future__ import annotations

from pathlib import Path

from harpy.config import DEFAULT_MODEL, load_config, resolve_model


def test_default_model_is_grok() -> None:
    assert DEFAULT_MODEL == "cursor-grok-4.6-high-fast"


def test_resolve_order() -> None:
    assert resolve_model() == (DEFAULT_MODEL, "default")
    assert resolve_model(file_model="other") == ("other", "toml")
    assert resolve_model(file_model="other", env={"HARPY_MODEL": "from-env"}) == (
        "from-env",
        "env",
    )
    assert resolve_model(cli_model="cli", env={"HARPY_MODEL": "from-env"}, file_model="x") == (
        "cli",
        "cli",
    )


def test_toml_default_matches_constant() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / ".harpy.toml").read_text(encoding="utf-8")
    assert f'model = "{DEFAULT_MODEL}"' in text
    loaded = load_config(start=root, env={})
    assert loaded.semantic.model == DEFAULT_MODEL


def test_toml_timeout_is_loaded() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_config(start=root, env={})
    assert loaded.semantic.timeout_seconds == 600.0
