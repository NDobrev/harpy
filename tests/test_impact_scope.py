from __future__ import annotations

from harpy.analysis.api_impact import extract_static_api_impacts
from harpy.analysis.impact_scope import enrich_contract_impacts
from harpy.models import (
    AnalysisResult,
    ChangedFile,
    DiffHunk,
    FileCategory,
    LogicalChange,
    PullRequest,
    StaticSignals,
)
from harpy.tui.impact_entries import entries_from_result, rows_from_entries, visible_impact_rows


def _pr() -> PullRequest:
    return PullRequest(
        number=1,
        title="fees",
        body="",
        base_ref="main",
        head_ref="f",
        head_sha="a",
        additions=1,
        deletions=1,
    )


def test_static_api_lists_files_and_business_logic() -> None:
    result = AnalysisResult(
        pr=_pr(),
        files=[
            ChangedFile(
                path="src/routes/v1.ts",
                status="modified",
                additions=1,
                deletions=1,
                category_scores={FileCategory.API: 0.75},
            ),
            ChangedFile(
                path="src/services/settle.ts",
                status="modified",
                additions=2,
                deletions=0,
                category_scores={FileCategory.BUSINESS_LOGIC: 0.7},
                business_logic_probability=0.7,
            ),
        ],
        hunks=[
            DiffHunk(
                id="H1",
                file_path="src/routes/v1.ts",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                patch='@@\n+  router.post("/v1/fees/ledger/:id/settle")\n',
            )
        ],
        changes=[
            LogicalChange(
                id="C1",
                title="settle",
                files=["src/routes/v1.ts", "src/services/settle.ts"],
                hunk_ids=["H1"],
                domains=["API"],
            )
        ],
        signals=[
            StaticSignals(
                file_path="src/routes/v1.ts", hunk_id="H1", api_change=True, categories=["API"]
            )
        ],
    )
    result.api_impacts = extract_static_api_impacts(result)
    enrich_contract_impacts(result)
    impact = result.api_impacts[0]
    assert "src/routes/v1.ts" in impact.files
    assert "src/services/settle.ts" in impact.files
    assert impact.business_logic
    assert "settle.ts" in impact.business_logic_why


def test_migration_only_is_not_business_logic() -> None:
    result = AnalysisResult(
        pr=_pr(),
        files=[
            ChangedFile(
                path="src/db/migrations/002.sql",
                status="modified",
                additions=1,
                deletions=0,
                category_scores={FileCategory.MIGRATION: 0.9},
            )
        ],
        hunks=[
            DiffHunk(
                id="H1",
                file_path="src/db/migrations/002.sql",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                patch="@@\n+ALTER TABLE fees.ledger ADD COLUMN settled_at timestamptz;\n",
            )
        ],
        changes=[
            LogicalChange(
                id="S1",
                title="src/db/migrations/002.sql",
                files=["src/db/migrations/002.sql"],
                hunk_ids=["H1"],
                domains=["MIGRATION"],
            )
        ],
        db_impacts=[],
    )
    from harpy.analysis.db_impact import extract_static_db_impacts

    result.db_impacts = extract_static_db_impacts(result)
    enrich_contract_impacts(result)
    assert result.db_impacts
    assert result.db_impacts[0].files == ["src/db/migrations/002.sql"]
    assert not result.db_impacts[0].business_logic


def test_impact_tree_nests_files_and_folds() -> None:
    result = AnalysisResult(
        pr=_pr(),
        api_impacts=[],
        db_impacts=[],
    )
    from harpy.models import ApiEndpointImpact

    result.api_impacts = [
        ApiEndpointImpact(
            method="POST",
            path="/v1/settle",
            summary="settle",
            files=["src/routes/v1.ts", "src/services/settle.ts"],
            business_logic=True,
            business_logic_why="fee state machine",
        )
    ]
    entries = entries_from_result(result)
    rows = rows_from_entries(entries)
    kinds = [row.kind for row in rows]
    assert kinds == ["impact", "file", "file"]
    assert "BL" in rows[0].label
    assert rows[1].file_path == "src/routes/v1.ts"
    assert rows[2].last
    folded = visible_impact_rows(rows, {rows[0].node_key})
    assert [row.kind for row in folded] == ["impact"]


def test_auth_file_sets_security_label() -> None:
    result = AnalysisResult(
        pr=_pr(),
        files=[
            ChangedFile(
                path="src/routes/v1.ts",
                status="modified",
                additions=1,
                deletions=0,
                category_scores={FileCategory.API: 0.75},
            ),
            ChangedFile(
                path="src/auth/permissions.ts",
                status="modified",
                additions=1,
                deletions=0,
                category_scores={FileCategory.AUTH: 0.8},
            ),
        ],
        hunks=[
            DiffHunk(
                id="H1",
                file_path="src/routes/v1.ts",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                patch='@@\n+  router.post("/v1/admin/grant")\n',
            )
        ],
        changes=[
            LogicalChange(
                id="C1",
                title="grant",
                files=["src/routes/v1.ts", "src/auth/permissions.ts"],
                hunk_ids=["H1"],
                domains=["API"],
                security_sensitivity=8,
            )
        ],
        signals=[
            StaticSignals(
                file_path="src/routes/v1.ts", hunk_id="H1", api_change=True, categories=["API"]
            )
        ],
    )
    result.api_impacts = extract_static_api_impacts(result)
    enrich_contract_impacts(result)
    impact = result.api_impacts[0]
    assert impact.security
    assert "permissions.ts" in impact.security_why
    rows = rows_from_entries(entries_from_result(result))
    assert "SEC" in rows[0].label
    assert rows[0].tone == "sec"
