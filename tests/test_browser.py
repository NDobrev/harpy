from __future__ import annotations

import json
from pathlib import Path

from harpy.analysis.pipeline import open_browser_selection
from harpy.analysis.workflows.browser import (
    history_for,
    list_browser,
    load_analysis,
    persist_analysis,
)
from harpy.analysis.workflows.session import OpenInbox, OpenReview
from harpy.config import HarpyConfig
from harpy.github.inbox import InboxPage, parse_inbox, query_inbox
from harpy.models import AnalysisResult, Freshness, LogicalChange, PullRequest
from harpy.proc import ProcResult


def _result(**kwargs: object) -> AnalysisResult:
    pr = PullRequest(
        number=int(str(kwargs.get("number", 42))),
        title=str(kwargs.get("title", "auth")),
        body="",
        base_ref="main",
        head_ref="f",
        head_sha=str(kwargs.get("head_sha", "aaaaaaaaaaaa")),
        additions=1,
        deletions=0,
        repo=str(kwargs.get("repo", "acme/pay")),
    )
    return AnalysisResult(
        pr=pr,
        changes=[LogicalChange(id="C1", title="auth")],
        workspace_path=str(kwargs.get("workspace_path", "")),
        scopes_run=["changes"],
    )


def _proc(stdout: str, *, ok: bool = True) -> ProcResult:
    return ProcResult(("gh",), 0 if ok else 1, stdout, "" if ok else "rate limited")


def test_headless_persist_is_browsable_from_another_store(tmp_path: Path) -> None:
    persist_analysis(_result(), root=tmp_path)
    again = list_browser("local", offline=True, root=tmp_path)
    assert len(again) == 1
    assert again[0].title == "auth"
    assert again[0].has_local_report
    loaded = load_analysis(again[0].review_id, root=tmp_path)  # type: ignore[arg-type]
    assert loaded is not None
    assert loaded.changes[0].title == "auth"


def test_expired_worktree_still_opens(tmp_path: Path) -> None:
    persist_analysis(_result(workspace_path=str(tmp_path / "gone")), root=tmp_path)
    item = list_browser("local", offline=True, root=tmp_path)[0]
    loaded = load_analysis(item.review_id, root=tmp_path)  # type: ignore[arg-type]
    assert loaded is not None
    assert loaded.workspace_path is None
    assert loaded.banner is not None
    assert "expired" in loaded.banner.lower()


def test_offline_inbox_does_not_call_network(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], **kwargs: object) -> ProcResult:
        calls.append(list(argv))
        raise AssertionError("offline must not call gh")

    rows = query_inbox("authored", offline=True, runner=runner, cached=InboxPage())
    listed = list_browser("authored", offline=True, root=tmp_path, runner=runner)
    assert rows.from_cache
    assert calls == []
    assert "clone" not in json.dumps([item.model_dump(mode="json") for item in listed])


def test_inbox_tabs_are_distinct() -> None:
    authored = parse_inbox(
        json.dumps(
            [
                {
                    "number": 1,
                    "title": "mine",
                    "repository": {"nameWithOwner": "acme/pay"},
                    "author": {"login": "me"},
                }
            ]
        ),
        tab="authored",
    )
    assigned = parse_inbox(
        json.dumps(
            [
                {
                    "number": 2,
                    "title": "theirs",
                    "repository": {"nameWithOwner": "acme/pay"},
                    "author": {"login": "you"},
                }
            ]
        ),
        tab="assigned",
    )
    requested = parse_inbox(
        json.dumps(
            [
                {
                    "number": 3,
                    "title": "review",
                    "repository": {"nameWithOwner": "acme/pay"},
                    "author": {"login": "x"},
                }
            ]
        ),
        tab="review-requested",
    )
    assert [row.tab for row in authored + assigned + requested] == [
        "authored",
        "assigned",
        "review-requested",
    ]
    assert {row.number for row in authored + assigned + requested} == {1, 2, 3}


def test_rate_limit_keeps_cached_rows() -> None:
    cached = InboxPage(
        rows=parse_inbox(
            json.dumps(
                [{"number": 9, "title": "kept", "repository": {"nameWithOwner": "acme/pay"}}]
            ),
            tab="authored",
        ),
        fetched_at="earlier",
    )
    page = query_inbox(
        "authored",
        runner=lambda argv, **kwargs: _proc("", ok=False),
        cached=cached,
    )
    assert page.from_cache
    assert page.rows[0].title == "kept"
    assert "rate limited" in page.error


def test_new_head_changes_freshness_not_report(tmp_path: Path) -> None:
    persist_analysis(_result(head_sha="aaaaaaaaaaaa"), root=tmp_path)
    payload = json.dumps(
        [
            {
                "number": 42,
                "title": "auth",
                "repository": {"nameWithOwner": "acme/pay"},
                "author": {"login": "me"},
                "updatedAt": "now",
            }
        ]
    )
    head = json.dumps({"headRefOid": "bbbbbbbbbbbb", "statusCheckRollup": []})

    def runner(argv: list[str], **kwargs: object) -> ProcResult:
        assert "clone" not in argv
        if "search" in argv:
            return _proc(payload)
        return _proc(head)

    items = list_browser(
        "authored", offline=False, root=tmp_path, runner=runner, refresh_remote=True
    )
    assert items[0].has_local_report
    assert items[0].freshness == Freshness.CODE_CHANGED
    assert items[0].analyzed_rev.startswith("a")
    loaded = load_analysis(items[0].review_id, root=tmp_path)  # type: ignore[arg-type]
    assert loaded is not None
    assert loaded.pr.head_sha.startswith("a")


def test_tracked_dedupes_same_pr(tmp_path: Path) -> None:
    persist_analysis(_result(), root=tmp_path)
    payload = json.dumps(
        [{"number": 42, "title": "auth", "repository": {"nameWithOwner": "acme/pay"}}]
    )

    def runner(argv: list[str], **kwargs: object) -> ProcResult:
        if "search" in argv:
            return _proc(payload)
        return _proc(json.dumps({"headRefOid": "aaaaaaaaaaaa"}))

    tracked = list_browser(
        "tracked", offline=False, root=tmp_path, runner=runner, refresh_remote=False
    )
    keys = [f"{item.repo}#{item.number}" for item in tracked if item.number is not None]
    assert keys.count("acme/pay#42") == 1


def test_history_matches_reference(tmp_path: Path) -> None:
    persist_analysis(_result(number=42, title="auth"), root=tmp_path)
    found = history_for("42", root=tmp_path)
    assert found
    assert found[0].number == 42


def test_query_inbox_argv_is_metadata_only() -> None:
    seen: list[list[str]] = []

    def runner(argv: list[str], **kwargs: object) -> ProcResult:
        seen.append(list(argv))
        return _proc("[]")

    query_inbox("authored", runner=runner)
    assert seen
    assert seen[0][:3] == ["gh", "search", "prs"]
    assert all("clone" not in argv and "worktree" not in argv for argv in seen)


def test_open_inbox_selection_runs_static_and_persists(
    config: HarpyConfig, fake_gh_path: Path, tmp_path: Path
) -> None:
    opened = open_browser_selection(
        OpenInbox(repo="acme/pay", number=1842, title="remote only"),
        config=config,
        root=tmp_path,
    )
    assert isinstance(opened, OpenReview)
    assert opened.result.pr.number == 1842
    assert opened.review_id is not None
    loaded = load_analysis(opened.review_id, root=tmp_path)
    assert loaded is not None
    assert loaded.pr.number == 1842
