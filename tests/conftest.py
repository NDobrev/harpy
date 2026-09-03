from __future__ import annotations

import os
from pathlib import Path

import pytest

from harpy.config import HarpyConfig, SemanticConfig
from harpy.models import ScoringWeights

ROOT = Path(__file__).resolve().parents[1]
FAKE_BIN = ROOT / "tests" / "fake_bin"


@pytest.fixture
def fake_gh_path(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PATH", f"{FAKE_BIN}{os.pathsep}{os.environ.get('PATH', '')}")
    return FAKE_BIN


@pytest.fixture
def config(tmp_path: Path) -> HarpyConfig:
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
