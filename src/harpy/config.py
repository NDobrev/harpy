"""Configuration and model resolution."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from harpy.models import ScoringWeights

DEFAULT_MODEL = "cursor-grok-4.6-high-fast"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "harpy"
CONFIG_NAME = ".harpy.toml"
SELECTABLE_MODELS = (
    DEFAULT_MODEL,
    "cursor-grok-4.5-high-fast",
    "claude-opus-5-thinking-high",
    "gpt-5.6-sol-high",
    "composer-2.5-fast",
)


@dataclass(frozen=True)
class SemanticConfig:
    model: str
    enabled: bool
    model_source: str
    timeout_seconds: float = 600.0


@dataclass(frozen=True)
class HarpyConfig:
    semantic: SemanticConfig
    scoring: ScoringWeights
    generated_globs: tuple[str, ...]
    high_impact: tuple[str, ...]
    low_impact: tuple[str, ...]
    cache_dir: Path
    path: Path | None
    selectable_models: tuple[str, ...] = SELECTABLE_MODELS


def with_model(config: HarpyConfig, model: str) -> HarpyConfig:
    return replace(config, semantic=replace(config.semantic, model=model, model_source="scope"))


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def find_config_file(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for folder in [current, *current.parents]:
        candidate = folder / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def resolve_model(
    *,
    cli_model: str | None = None,
    env: dict[str, str] | None = None,
    file_model: str | None = None,
) -> tuple[str, str]:
    """Highest wins: --model, HARPY_MODEL, .harpy.toml, DEFAULT_MODEL."""
    if cli_model:
        return cli_model, "cli"
    environ = env if env is not None else os.environ
    if environ.get("HARPY_MODEL"):
        return environ["HARPY_MODEL"], "env"
    if file_model:
        return file_model, "toml"
    return DEFAULT_MODEL, "default"


def load_config(
    *,
    start: Path | None = None,
    cli_model: str | None = None,
    env: dict[str, str] | None = None,
) -> HarpyConfig:
    path = find_config_file(start)
    data = _read_toml(path) if path else {}
    semantic = data.get("semantic", {})
    scoring_data = data.get("scoring", {})
    paths = data.get("paths", {})
    file_model = semantic.get("model") if isinstance(semantic, dict) else None
    model, source = resolve_model(cli_model=cli_model, env=env, file_model=file_model)
    enabled = True
    timeout_seconds = 600.0
    selectable: tuple[str, ...] = SELECTABLE_MODELS
    if isinstance(semantic, dict):
        if "enabled" in semantic:
            enabled = bool(semantic["enabled"])
        if "timeout_seconds" in semantic:
            timeout_seconds = float(semantic["timeout_seconds"])
        raw_models = semantic.get("models")
        if isinstance(raw_models, list) and raw_models:
            selectable = tuple(str(item) for item in raw_models)
    weights = ScoringWeights.model_validate(scoring_data) if scoring_data else ScoringWeights()
    generated = tuple(paths.get("generated", ())) if isinstance(paths, dict) else ()
    high = tuple(paths.get("high_impact", ())) if isinstance(paths, dict) else ()
    low = tuple(paths.get("low_impact", ())) if isinstance(paths, dict) else ()
    return HarpyConfig(
        semantic=SemanticConfig(
            model=model,
            enabled=enabled,
            model_source=source,
            timeout_seconds=timeout_seconds,
        ),
        scoring=weights,
        generated_globs=generated,
        high_impact=high,
        low_impact=low,
        cache_dir=DEFAULT_CACHE_DIR,
        path=path,
        selectable_models=selectable,
    )


def default_toml_text(config: HarpyConfig) -> str:
    return (
        "[semantic]\n"
        f'model = "{config.semantic.model}"\n'
        f"enabled = {str(config.semantic.enabled).lower()}\n"
        "\n"
        "[scoring]\n"
        f"auth_change = {config.scoring.auth_change:g}\n"
        f"api_change = {config.scoring.api_change:g}\n"
        f"migration = {config.scoring.migration:g}\n"
        f"generated = {config.scoring.generated:g}\n"
        f"lockfile = {config.scoring.lockfile:g}\n"
    )
