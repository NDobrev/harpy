from __future__ import annotations

from pathlib import Path

from harpy.analysis.db_impact import extract_static_db_impacts, looks_like_db
from harpy.analysis.pipeline import apply_semantic
from harpy.config import HarpyConfig, SemanticConfig
from harpy.models import (
    AnalysisResult,
    ApiDiagram,
    ChangedFile,
    DbChangeImpact,
    DiffHunk,
    FileCategory,
    PullRequest,
    SemanticAnalysisResult,
    SemanticChangeDraft,
    StaticSignals,
)
from harpy.tui.impact_entries import entries_from_result


def _pr() -> PullRequest:
    return PullRequest(
        number=1,
        title="ledger",
        body="",
        base_ref="main",
        head_ref="f",
        head_sha="a",
        additions=1,
        deletions=1,
    )


def _result(
    hunks: list[DiffHunk],
    *,
    path: str = "src/db/migrations/002_settle.sql",
    category: FileCategory = FileCategory.MIGRATION,
    migration: bool = True,
) -> AnalysisResult:
    return AnalysisResult(
        pr=_pr(),
        files=[
            ChangedFile(
                path=path,
                status="modified",
                additions=1,
                deletions=1,
                category_scores={category: 0.9},
            )
        ],
        hunks=hunks,
        signals=[
            StaticSignals(
                file_path=path,
                hunk_id="H1",
                migration=migration,
                db_change=True,
                categories=[category.value],
            )
        ],
    )


def test_static_extraction_finds_add_and_drop() -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="src/db/migrations/002_settle.sql",
        old_start=1,
        old_count=2,
        new_start=1,
        new_count=3,
        patch=(
            "@@\n"
            "+DROP TABLE fee_pending;\n"
            "+ALTER TABLE fees.ledger ADD COLUMN settled_at timestamptz;\n"
            "+CREATE TABLE fees.settle_audit (id uuid);\n"
        ),
    )
    result = _result([hunk])
    assert looks_like_db(result)
    impacts = extract_static_db_impacts(result)
    targets = {item.target for item in impacts}
    assert "fee_pending" in targets
    assert "fees.ledger.settled_at" in targets
    assert "fees.settle_audit" in targets
    dropped = next(item for item in impacts if item.target == "fee_pending")
    assert dropped.breaking
    assert dropped.operation == "drop_table"
    assert all(not item.diagrams for item in impacts)


def test_two_alter_tables_do_not_cross_product_columns() -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="src/db/migrations/003_two_alters.sql",
        old_start=1,
        old_count=1,
        new_start=1,
        new_count=2,
        patch=(
            "@@\n"
            "+ALTER TABLE fees.ledger ADD COLUMN settled_at timestamptz;\n"
            "+ALTER TABLE users ADD COLUMN email text;\n"
        ),
    )
    result = _result([hunk], path="src/db/migrations/003_two_alters.sql")
    impacts = extract_static_db_impacts(result)
    targets = {item.target for item in impacts}
    assert "fees.ledger.settled_at" in targets
    assert "users.email" in targets
    assert "fees.ledger.email" not in targets
    assert "users.settled_at" not in targets


def test_docs_only_change_is_not_db_impact() -> None:
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
        pr=_pr(),
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
    assert not looks_like_db(result)
    assert extract_static_db_impacts(result) == []


def test_repository_query_tweak_is_not_schema_impact() -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="src/repositories/fees.py",
        old_start=1,
        old_count=1,
        new_start=1,
        new_count=1,
        patch="@@\n+rows = session.query(Fee).filter_by(id=fee_id)\n",
    )
    result = AnalysisResult(
        pr=_pr(),
        files=[
            ChangedFile(
                path="src/repositories/fees.py",
                status="modified",
                additions=1,
                deletions=0,
                category_scores={FileCategory.DATA: 0.7},
            )
        ],
        hunks=[hunk],
        signals=[
            StaticSignals(
                file_path="src/repositories/fees.py",
                hunk_id="H1",
                db_change=True,
                categories=["DATA"],
            )
        ],
    )
    assert not looks_like_db(result)
    assert extract_static_db_impacts(result) == []


class _DbSemantic:
    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        assert prompt
        assert workspace
        return SemanticAnalysisResult(
            pr_intent="ledger settle column",
            changes=[
                SemanticChangeDraft(
                    id="C1",
                    title="settle column",
                    hunk_ids=["H1"],
                    files=["src/db/migrations/002_settle.sql"],
                )
            ],
            db_impacts=[
                DbChangeImpact(
                    change_id="C1",
                    operation="add_column",
                    target="fees.ledger.settled_at",
                    summary="stamp when an ops user settles a pending row",
                    before="ledger rows had no settle timestamp",
                    after="settled_at is set on off-band settle and stays null otherwise",
                    impact="readers that assumed write-once rows must tolerate a later stamp",
                    breaking=False,
                    objects=["fees.ledger.settled_at"],
                    diagrams=[
                        ApiDiagram(
                            kind="er",
                            title="ledger after settle",
                            mermaid="erDiagram\n  LEDGER ||--o| SETTLE : stamps",
                            why="the new nullable stamp is the only persistence contract change",
                        )
                    ],
                )
            ],
        )


def test_semantic_db_impacts_replace_static(config: HarpyConfig, tmp_path: Path) -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="src/db/migrations/002_settle.sql",
        old_start=1,
        old_count=1,
        new_start=1,
        new_count=1,
        patch="@@\n+ALTER TABLE fees.ledger ADD COLUMN settled_at timestamptz;\n",
    )
    result = _result([hunk])
    result.db_impacts = extract_static_db_impacts(result)
    result.pending_semantic = True
    result.workspace_path = str(tmp_path / "ws")
    result.analysis_key = "db-test"
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
        cache_dir=tmp_path / "cache-db",
        path=None,
    )
    updated = apply_semantic(result, config=enabled, semantic_client=_DbSemantic(), use_cache=False)
    assert updated.db_impacts
    assert updated.db_impacts[0].target == "fees.ledger.settled_at"
    assert updated.db_impacts[0].diagrams
    assert updated.db_impacts[0].diagrams[0].kind == "er"
    assert updated.db_impacts[0].before
    rows = entries_from_result(updated)
    assert len(rows) == 1
    assert rows[0].kind == "db"
    assert rows[0].diagrams[0].kind == "er"
