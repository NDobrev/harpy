from __future__ import annotations

from harpy.models import ChangedFile, DiffHunk, FileCategory, SemanticChangeDraft, StaticSignals
from harpy.semantic.prompts import (
    CONTEXT_FILENAME,
    build_bundle,
    context_filename,
    short_prompt,
)
from harpy.semantic.scopes import compose_instruction


def test_compose_includes_only_selected_sections() -> None:
    api_only = compose_instruction(["api"], with_changes=False)
    assert '"api_impacts"' in api_only
    assert '"db_impacts"' not in api_only
    assert '"changes"' not in api_only
    assert "KNOWN CHANGES" in api_only or "Do not regroup" in api_only


def test_inline_fields_when_sharing_changes_call() -> None:
    text = compose_instruction(["changes", "security", "questions", "tests", "omissions"])
    assert '"changes"' in text
    assert '"security_sensitivity"' in text
    assert '"review_questions"' in text
    assert '"annotations"' not in text


def test_annotations_block_when_scopes_are_standalone() -> None:
    text = compose_instruction(["security", "questions"], with_changes=False)
    assert '"annotations"' in text
    assert '"change_id"' in text
    assert '"security_sensitivity"' in text
    assert '"review_questions"' in text
    assert '"changes"' not in text


def test_diagrams_only_on_contract_calls() -> None:
    with_diagrams = compose_instruction(["api", "diagrams"], with_changes=False)
    without = compose_instruction(["api"], with_changes=False)
    assert '"sequence"' in with_diagrams
    assert '"sequence"' not in without


def test_context_filenames_are_distinct() -> None:
    assert context_filename() == CONTEXT_FILENAME
    assert context_filename("c0") == "ANALYSIS_CONTEXT_c0.md"
    assert context_filename("c1") == "ANALYSIS_CONTEXT_c1.md"
    assert context_filename("c0") != context_filename("c1")
    assert "c0" in short_prompt("ANALYSIS_CONTEXT_c0.md")


def test_build_bundle_default_matches_unscoped_shape() -> None:
    files = [
        ChangedFile(
            path="src/fees.ts",
            status="modified",
            additions=1,
            deletions=0,
            category_scores={category.value: 0.0 for category in FileCategory},
        )
    ]
    hunks = [
        DiffHunk(
            id="H1",
            file_path="src/fees.ts",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            patch="@@ hunk @@\n+line\n",
            static_score=1,
        )
    ]
    signals = [
        StaticSignals(
            file_path="src/fees.ts", hunk_id="H1", raw_score=1, categories=["BUSINESS_LOGIC"]
        )
    ]
    default_bundle = build_bundle(
        title="Fix fees",
        body="summary",
        files=files,
        hunks=hunks,
        signals=signals,
        references=[],
    )
    scoped = build_bundle(
        title="Fix fees",
        body="summary",
        files=files,
        hunks=hunks,
        signals=signals,
        references=[],
        scope_ids=["api"],
        known_changes=[SemanticChangeDraft(id="C1", title="fees", hunk_ids=["H1"])],
        context_name="ANALYSIS_CONTEXT_c1.md",
    )
    assert "PROMPT_VERSION=11" in default_bundle
    assert "CHANGE H1" in default_bundle
    assert "KNOWN CHANGES" in scoped
    assert "- C1 fees hunks=['H1']" in scoped
    assert "ANALYSIS_CONTEXT_c1.md" in scoped
    assert '"api_impacts"' in scoped
    assert '"db_impacts"' not in scoped
