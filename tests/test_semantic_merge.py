from __future__ import annotations

from harpy.analysis.semantic_merge import fold_annotations, merge_semantic
from harpy.models import ChangeAnnotation, ScopeCall, SemanticAnalysisResult, SemanticChangeDraft


def _call(*scope_ids: str, model: str = "cursor-grok-4.6-high-fast") -> ScopeCall:
    return ScopeCall(id="c0", model=model, scope_ids=list(scope_ids), stage=0, context_name="x.md")


def test_annotations_fold_onto_matching_drafts() -> None:
    drafts = [
        SemanticChangeDraft(id="C1", title="auth", hunk_ids=["H1"]),
        SemanticChangeDraft(id="C2", title="docs", hunk_ids=["H2"]),
    ]
    folded = fold_annotations(
        drafts,
        [
            ChangeAnnotation(
                change_id="C1",
                security_sensitivity=9,
                review_questions=["who?"],
                tests=["tests/test_auth.py"],
            )
        ],
    )
    assert folded[0].security_sensitivity == 9
    assert folded[0].review_questions == ["who?"]
    assert folded[0].tests == ["tests/test_auth.py"]
    assert folded[1].security_sensitivity == 0


def test_partial_degradation_keeps_successful_scopes() -> None:
    ok = SemanticAnalysisResult(
        pr_intent="fees",
        changes=[SemanticChangeDraft(id="C1", title="fees", hunk_ids=["H1"])],
    )
    failed = SemanticAnalysisResult(degraded=True, error="timeout")
    merged = merge_semantic(
        [
            (_call("changes"), ok),
            (_call("api", model="gpt-5.6-sol-high"), failed),
        ]
    )
    assert merged.degraded is False
    assert merged.changes[0].title == "fees"
    assert merged.error is not None
    assert "api" in merged.error
    assert merged.api_impacts == []


def test_all_calls_degraded() -> None:
    merged = merge_semantic(
        [
            (_call("changes"), SemanticAnalysisResult(degraded=True, error="a")),
            (_call("api"), SemanticAnalysisResult(degraded=True, error="b")),
        ]
    )
    assert merged.degraded is True
    assert merged.changes == []
    assert merged.error is not None
