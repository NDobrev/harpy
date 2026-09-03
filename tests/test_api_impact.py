from __future__ import annotations

from pathlib import Path

from harpy.analysis.api_impact import extract_static_api_impacts, looks_like_api
from harpy.analysis.pipeline import apply_semantic
from harpy.config import HarpyConfig, SemanticConfig
from harpy.models import (
    AnalysisResult,
    ApiDiagram,
    ApiEndpointImpact,
    ChangedFile,
    DiffHunk,
    FileCategory,
    PullRequest,
    SemanticAnalysisResult,
    SemanticChangeDraft,
    StaticSignals,
)


def _result(hunks: list[DiffHunk], *, api_path: str = "src/routes/v1.ts") -> AnalysisResult:
    return AnalysisResult(
        pr=PullRequest(
            number=1,
            title="fees",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="a",
            additions=1,
            deletions=1,
        ),
        files=[
            ChangedFile(
                path=api_path,
                status="modified",
                additions=1,
                deletions=1,
                category_scores={FileCategory.API: 0.75},
            )
        ],
        hunks=hunks,
        signals=[
            StaticSignals(file_path=api_path, hunk_id="H1", api_change=True, categories=["API"])
        ],
    )


def test_static_extraction_finds_route_and_deleted_contract() -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="src/routes/v1.ts",
        old_start=1,
        old_count=2,
        new_start=1,
        new_count=2,
        patch='@@\n-  router.get("/v1/old")\n+  "/v1/fees/ledger/:id/settle": {\n',
    )
    result = _result([hunk])
    assert looks_like_api(result)
    impacts = extract_static_api_impacts(result)
    paths = {item.path for item in impacts}
    assert "/v1/old" in paths
    assert "/v1/fees/ledger/:id/settle" in paths
    deleted = next(item for item in impacts if item.path == "/v1/old")
    assert deleted.breaking
    assert all(not item.diagrams for item in impacts)


def test_docs_only_change_is_not_api_impact() -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="docs/readme.md",
        old_start=1,
        old_count=1,
        new_start=1,
        new_count=1,
        patch="@@\n+hello\n",
    )
    result = AnalysisResult(
        pr=_result([]).pr,
        files=[
            ChangedFile(
                path="docs/readme.md",
                status="modified",
                additions=1,
                deletions=0,
                category_scores={FileCategory.DOCUMENTATION: 0.85},
            )
        ],
        hunks=[hunk],
        signals=[
            StaticSignals(file_path="docs/readme.md", hunk_id="H1", categories=["DOCUMENTATION"])
        ],
    )
    assert not looks_like_api(result)
    assert extract_static_api_impacts(result) == []


class _ApiSemantic:
    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        assert prompt
        return SemanticAnalysisResult(
            pr_intent="fees",
            changes=[
                SemanticChangeDraft(
                    id="C1",
                    title="off-band settle",
                    hunk_ids=["H1"],
                    files=["src/routes/v1.ts"],
                )
            ],
            api_impacts=[
                ApiEndpointImpact(
                    change_id="C1",
                    method="POST",
                    path="/v1/fees/ledger/:id/settle",
                    summary="ops settle a pending fee row",
                    before="XRP fee rows stayed pending forever",
                    after="beneficiary or ancestor can stamp off_band",
                    impact="ops workflow; ledger is no longer write-once",
                    breaking=False,
                    diagrams=[
                        ApiDiagram(
                            kind="sequence",
                            title="off-band settle",
                            mermaid="sequenceDiagram\n  Ops->>API: POST settle\n  API->>Ledger: stamp",
                            why="the settle path is a new actor the payout flow does not have",
                        )
                    ],
                )
            ],
        )


def test_semantic_api_impacts_replace_static(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    from harpy.analysis.pipeline import analyze_static

    enabled = HarpyConfig(
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
        cache_dir=tmp_path / "cache-api",
        path=None,
    )
    draft = analyze_static("1842", config=enabled, use_ai=True, use_cache=False)
    draft.pending_semantic = True
    result = apply_semantic(draft, config=enabled, semantic_client=_ApiSemantic(), use_cache=False)
    assert result.api_impacts
    assert result.api_impacts[0].path == "/v1/fees/ledger/:id/settle"
    assert result.api_impacts[0].diagrams
    assert result.api_impacts[0].diagrams[0].kind == "sequence"
