"""Merge per-call semantic results and fold standalone annotations into drafts."""

from __future__ import annotations

from harpy.models import (
    ApiEndpointImpact,
    ChangeAnnotation,
    DbChangeImpact,
    ScopeCall,
    SemanticAnalysisResult,
    SemanticChangeDraft,
)


def apply_annotation(
    draft: SemanticChangeDraft, annotation: ChangeAnnotation
) -> SemanticChangeDraft:
    data = draft.model_dump()
    if annotation.security_sensitivity is not None:
        data["security_sensitivity"] = annotation.security_sensitivity
    if annotation.data_sensitivity is not None:
        data["data_sensitivity"] = annotation.data_sensitivity
    if annotation.review_questions is not None:
        data["review_questions"] = annotation.review_questions
    if annotation.tests is not None:
        data["tests"] = annotation.tests
    if annotation.possible_omissions is not None:
        data["possible_omissions"] = annotation.possible_omissions
    return SemanticChangeDraft.model_validate(data)


def fold_annotations(
    drafts: list[SemanticChangeDraft], annotations: list[ChangeAnnotation]
) -> list[SemanticChangeDraft]:
    by_id = {item.change_id: item for item in annotations}
    return [
        apply_annotation(draft, by_id[draft.id]) if draft.id in by_id else draft for draft in drafts
    ]


def merge_semantic(
    pairs: list[tuple[ScopeCall, SemanticAnalysisResult]],
) -> SemanticAnalysisResult:
    if not pairs:
        return SemanticAnalysisResult()
    pr_intent = ""
    drafts: list[SemanticChangeDraft] = []
    api: list[ApiEndpointImpact] = []
    db: list[DbChangeImpact] = []
    annotations: list[ChangeAnnotation] = []
    failed: list[str] = []
    for call, result in pairs:
        if result.degraded:
            failed.extend(call.scope_ids)
            continue
        if result.pr_intent and not pr_intent:
            pr_intent = result.pr_intent
        if result.changes:
            drafts = result.changes
        api.extend(result.api_impacts)
        db.extend(result.db_impacts)
        annotations.extend(result.annotations)
    drafts = fold_annotations(drafts, annotations)
    error = f"degraded scopes: {','.join(sorted(set(failed)))}" if failed else None
    all_failed = bool(failed) and all(result.degraded for _, result in pairs)
    return SemanticAnalysisResult(
        pr_intent=pr_intent,
        changes=drafts,
        api_impacts=api,
        db_impacts=db,
        annotations=annotations,
        degraded=all_failed,
        error=error,
    )
