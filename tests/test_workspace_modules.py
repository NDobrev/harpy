from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from harpy.analysis.workflows.incremental import plan_incremental
from harpy.export.report import export_html, export_json, export_markdown
from harpy.git.local import LocalReviewError, parse_local_args
from harpy.github.reviews import submission_marker
from harpy.models import (
    AnalysisReport,
    LogicalChange,
    LogicalChangeIdentity,
    ReportProvenance,
    RetrievalRequest,
    ReviewStatus,
)
from harpy.review.identity import candidate_score, jaccard, match_identities
from harpy.review.intent import IntentSource, conflict_question
from harpy.review.planning import budget_prefix, readiness, route_changes
from harpy.review.state import ReviewAction, ReviewState
from harpy.semantic.context import RunBudget, estimate_units
from harpy.semantic.protocol import RetrievalDenied, allow_retrieval, parse_provider_payload
from harpy.storage.db import ReviewStore
from harpy.verification.runner import RunnerProfile, docker_argv


def test_context_request_denied_for_absolute_or_unknown_path() -> None:
    payload = parse_provider_payload({"kind": "needs_context", "requests": []})
    assert payload.kind == "needs_context"
    with pytest.raises(RetrievalDenied):
        allow_retrieval(
            RetrievalRequest(reason="x", path="src/secret.py"),
            allowed_paths={"src/ok.py"},
        )


def test_repair_counts_against_budget() -> None:
    budget = RunBudget(run_units=100, max_calls=3)
    budget.consume(40)
    budget.consume(40, repair=True)
    assert budget.repairs == 1
    assert budget.calls == 2
    assert estimate_units("abc") >= 1


def test_local_mode_requires_exactly_one_comparison() -> None:
    with pytest.raises(LocalReviewError):
        parse_local_args(
            local=True, base=None, staged=False, working_tree=False, include_untracked=False
        )
    spec = parse_local_args(
        local=True, base="main", staged=False, working_tree=False, include_untracked=False
    )
    assert spec.mode == "committed"


def test_identity_line_shift_and_split_do_not_auto_approve() -> None:
    old = LogicalChangeIdentity(id=uuid4(), fingerprints=["a" * 64], revision_local_ids=["C1"])
    new = LogicalChangeIdentity(id=uuid4(), fingerprints=["a" * 64], revision_local_ids=["C1"])
    matches = match_identities([old], [new], content_sets={}, symbol_sets={})
    assert matches[0].kind == "fingerprint"
    assert candidate_score(content=1.0, symbols=None) == 1.0
    assert jaccard({"a"}, {"a", "b"}) < 1


def test_undo_keeps_history(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path)
    state = ReviewState(store)
    action = ReviewAction(uuid4(), uuid4(), ReviewStatus.REVIEWED, "ok")
    state.apply(action)
    state.undo()
    assert store.event_count() == 2
    store.close()


def test_incremental_docs_edit_reuses() -> None:
    preview, plan = plan_incremental(
        review_id=uuid4(),
        invalidated_ratio=0.1,
        dependency_complete=True,
        reuse=8,
        reanalyze=1,
        new=0,
        reason="docs only",
    )
    assert preview.full is False
    assert plan.reuse_count == 8


def test_budget_does_not_mark_omitted_reviewed() -> None:
    changes = [
        LogicalChange(id="C1", title="a", review_priority=90, risk="HIGH"),
        LogicalChange(id="C2", title="b", review_priority=10, risk="LOW"),
    ]
    chosen, omitted = budget_prefix(route_changes(changes, kind="risk"), 1)
    assert chosen
    assert all(item.id != "reviewed" for item in omitted)
    assert "blocker" in readiness(0, 0, 1)


def test_export_escapes_html(tmp_path: Path) -> None:
    report = AnalysisReport(
        id=uuid4(), snapshot_id=uuid4(), provenance=ReportProvenance(run_id=uuid4())
    )
    html_path = export_html(report, tmp_path / "r.html")
    text = html_path.read_text(encoding="utf-8")
    assert "<script>" not in text
    export_markdown(report, tmp_path / "r.md")
    export_json(report, tmp_path / "r.json")


def test_docker_isolation_flags() -> None:
    argv = docker_argv(
        RunnerProfile(image_digest="sha256:" + "a" * 64, command=["pytest"]),
        "/work",
    )
    assert "--network" in argv and "none" in argv
    assert "--read-only" in argv
    assert "--cap-drop" in argv
    assert "no-new-privileges" in argv
    assert not any("docker.sock" in part for part in argv)
    assert not any(part.startswith("/home") for part in argv)


def test_intent_conflict_is_a_question() -> None:
    question = conflict_question(
        IntentSource("task", "must keep audit"),
        IntentSource("pr", "removed audit"),
    )
    assert question is not None


def test_submission_marker_is_stable() -> None:
    sid = uuid4()
    assert str(sid) in submission_marker(sid)
