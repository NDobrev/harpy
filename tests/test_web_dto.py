from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from harpy.models import ReviewStatus
from harpy.web.context import RequestContext
from harpy.web.dto import (
    CALL_SCOPE_IDS,
    SCOPE_IDS,
    ChangeSummary,
    OpenTargetRequest,
    ReviewProgress,
    SaveNoteRequest,
    ScopeSelection,
    TargetKind,
    WebRisk,
)


def _selection() -> ScopeSelection:
    return ScopeSelection(
        enabled={scope_id: True for scope_id in SCOPE_IDS},
        models={scope_id: "cursor-grok-4.6-high-fast" for scope_id in CALL_SCOPE_IDS},
        preset="Everything",
    )


def test_scope_selection_requires_all_ids() -> None:
    with pytest.raises(ValidationError):
        ScopeSelection(enabled={"changes": True}, models={"changes": "x"})


def test_scope_selection_rejects_unknown_fields() -> None:
    payload = _selection().model_dump()
    payload["extra"] = True
    with pytest.raises(ValidationError):
        ScopeSelection.model_validate(payload)


def test_open_target_requires_pr_number() -> None:
    with pytest.raises(ValidationError):
        OpenTargetRequest(repository_id=uuid4(), kind=TargetKind.GITHUB_PR)


def test_open_target_committed_requires_base_ref() -> None:
    with pytest.raises(ValidationError):
        OpenTargetRequest(repository_id=uuid4(), kind=TargetKind.LOCAL_COMMITTED)


def test_note_rejects_overlong_text() -> None:
    with pytest.raises(ValidationError):
        SaveNoteRequest(text="n" * 20_001, expected_version=0)


def test_progress_counts_must_sum() -> None:
    with pytest.raises(ValidationError):
        ReviewProgress(
            reviewed=1,
            question=0,
            blocker=0,
            unreviewed=0,
            total=2,
            report_id=uuid4(),
        )


def test_change_summary_uses_lowercase_risk() -> None:
    change = ChangeSummary(
        change_id=uuid4(),
        local_id="C1",
        title="Auth gate",
        rank_index=0,
        importance=80,
        unexpectedness=40,
        confidence=0.7,
        risk=WebRisk.HIGH,
        file_count=2,
        hunk_count=3,
        noise=False,
        status=ReviewStatus.UNREVIEWED,
        decision_version=0,
        note_present=False,
    )
    assert change.model_dump()["risk"] == "high"


def test_request_context_is_frozen() -> None:
    context = RequestContext(
        tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        actor_id=UUID("22222222-2222-4222-8222-222222222222"),
        role="reviewer",
        correlation_id=uuid4(),
        authenticated_subject="local",
        authorization_version=1,
    )
    with pytest.raises(ValidationError):
        context.actor_id = uuid4()


def test_valid_selection_round_trips() -> None:
    dumped = _selection().model_dump()
    assert ScopeSelection.model_validate(dumped).preset == "Everything"
    assert dumped["enabled"]["diagrams"] is True
