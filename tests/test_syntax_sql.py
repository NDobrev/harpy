from __future__ import annotations

from pathlib import Path

from harpy.analysis.db_impact import extract_static_db_impacts, looks_like_db
from harpy.analysis.syntax.extract import extract_file_facts
from harpy.models import (
    AnalysisResult,
    ChangedFile,
    DiffHunk,
    FileCategory,
    PullRequest,
    StaticSignals,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "syntax"


def test_sql_ddl_facts_scope_columns_to_their_table() -> None:
    source = (FIXTURES / "ledger.sql").read_text(encoding="utf-8")
    facts = extract_file_facts(source, path="migrations/001_ledger.sql")
    operations = {(item.operation, item.table, item.column) for item in facts.ddl}
    assert ("add_table", "fees.ledger", "") in operations
    assert ("add_column", "fees.ledger", "settled_at") in operations
    assert ("add_column", "users", "email") in operations
    assert ("drop_table", "fee_pending", "") in operations
    assert ("add_column", "fees.ledger", "email") not in operations
    assert ("add_column", "users", "settled_at") not in operations
    settled = next(item for item in facts.ddl if item.column == "settled_at")
    assert "timestamptz" in settled.col_type


def test_db_impact_prefers_sql_facts_over_regex() -> None:
    source = (FIXTURES / "ledger.sql").read_text(encoding="utf-8")
    facts = extract_file_facts(source, path="migrations/001_ledger.sql")
    result = AnalysisResult(
        pr=PullRequest(
            number=1,
            title="ledger",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="a",
            additions=1,
            deletions=1,
        ),
        files=[
            ChangedFile(
                path="migrations/001_ledger.sql",
                status="modified",
                additions=4,
                deletions=0,
                category_scores={FileCategory.MIGRATION: 0.9},
            )
        ],
        hunks=[
            DiffHunk(
                id="H1",
                file_path="migrations/001_ledger.sql",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=8,
                patch="@@\n+" + source.replace("\n", "\n+"),
            )
        ],
        signals=[
            StaticSignals(
                file_path="migrations/001_ledger.sql",
                hunk_id="H1",
                migration=True,
                db_change=True,
                categories=["MIGRATION"],
            )
        ],
        file_facts=[facts],
    )
    assert looks_like_db(result)
    targets = {item.target for item in extract_static_db_impacts(result)}
    assert "fees.ledger.settled_at" in targets
    assert "users.email" in targets
    assert "fees.ledger.email" not in targets
    assert "fee_pending" in targets
