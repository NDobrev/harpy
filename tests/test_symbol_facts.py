from __future__ import annotations

from pathlib import Path

from harpy.analysis.pipeline import apply_semantic
from harpy.config import HarpyConfig, SemanticConfig
from harpy.models import (
    AnalysisResult,
    FileFacts,
    ImportFact,
    PullRequest,
    RouteFact,
    ScoringWeights,
    SemanticAnalysisResult,
    SymbolFact,
)
from harpy.semantic.facts import FACTS_FILENAME, render_symbol_facts
from harpy.semantic.scopes import compose_instruction


def test_render_symbol_facts_is_greppable_by_path() -> None:
    text = render_symbol_facts(
        [
            FileFacts(
                path="src/api/users.ts",
                language="typescript",
                symbols=[
                    SymbolFact(
                        name="deleteUser",
                        kind="function",
                        start_line=41,
                        end_line=58,
                        visibility="public",
                        signature="export function deleteUser(id: string)",
                    )
                ],
                imports=[ImportFact(line=1, module="./db", names=["getPool"])],
                routes=[
                    RouteFact(line=44, method="DELETE", route="/v1/users/:id", handler="deleteUser")
                ],
            )
        ]
    )
    assert "## src/api/users.ts" in text
    assert "DEF  src/api/users.ts:41-58 function deleteUser public" in text
    assert "IMP  src/api/users.ts:1 module=./db names=[getPool]" in text
    assert "ROUTE src/api/users.ts:44 DELETE /v1/users/:id handler=deleteUser" in text


def test_facts_rule_is_scope_gated() -> None:
    with_facts = compose_instruction(["changes"])
    without = compose_instruction(["questions"], with_changes=False)
    assert "SYMBOL_FACTS.md" in with_facts
    assert "SYMBOL_FACTS.md" not in without


class _EmptySemantic:
    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        assert (workspace / FACTS_FILENAME).is_file()
        return SemanticAnalysisResult(degraded=True, error="skip")


def test_apply_semantic_writes_sidecar_once(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    result = AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="a",
            additions=1,
            deletions=0,
        ),
        pending_semantic=True,
        workspace_path=str(workspace),
        file_facts=[
            FileFacts(
                path="src/a.py",
                language="python",
                symbols=[SymbolFact(name="fn", kind="function", start_line=1, end_line=2)],
            )
        ],
    )
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
    apply_semantic(result, config=config, semantic_client=_EmptySemantic(), use_cache=False)
    written = (workspace / FACTS_FILENAME).read_text(encoding="utf-8")
    assert "DEF  src/a.py:1-2 function fn" in written
