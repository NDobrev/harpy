from __future__ import annotations

import json
from pathlib import Path

import pytest

from harpy.config import HarpyConfig, SemanticConfig
from harpy.models import ScoringWeights
from harpy.proc import ProcResult
from harpy.semantic.client import CursorAgentClient
from harpy.semantic.prompts import CONTEXT_FILENAME, SHORT_PROMPT


def test_client_writes_context_file_and_keeps_argv_short(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **_kwargs: object) -> ProcResult:
        captured["argv"] = list(argv)
        payload = {
            "type": "result",
            "subtype": "success",
            "result": json.dumps({"pr_intent": "fees", "changes": []}),
        }
        return ProcResult(argv=tuple(argv), returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("harpy.semantic.client.run", fake_run)
    config = HarpyConfig(
        semantic=SemanticConfig(
            model="cursor-grok-4.6-high-fast",
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
    workspace = tmp_path / "workspace"
    long_bundle = "PROMPT_VERSION=2\n" + ("HUNK\n" * 200)
    result = CursorAgentClient(config).analyze_text(long_bundle, workspace=workspace)
    assert result.pr_intent == "fees"
    assert (workspace / CONTEXT_FILENAME).read_text(encoding="utf-8") == long_bundle
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert argv[-1] == SHORT_PROMPT
    assert long_bundle not in argv
    assert sum(len(part) for part in argv) < 4000
