from __future__ import annotations

from pathlib import Path

import pytest

from harpy.analysis.workflows.browser import persist_analysis
from harpy.analysis.workflows.session import OpenInbox, OpenReview
from harpy.models import AnalysisResult, BrowserItem, LogicalChange, PullRequest
from harpy.prefs import PrefsStore
from harpy.storage.catalog import BrowserCatalog
from harpy.tui.browser_rows import filter_disabled, rows_from_items, visible_browser_rows
from harpy.tui.screens.browser import BrowserApp
from harpy.tui.screens.repo_filter import RepoFilterDialog


def _result() -> AnalysisResult:
    return AnalysisResult(
        pr=PullRequest(
            number=7,
            title="fees",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="abcabcabcabc",
            additions=1,
            deletions=0,
            repo="acme/pay",
        ),
        changes=[LogicalChange(id="C1", title="fees")],
    )


@pytest.mark.asyncio
async def test_browser_opens_persisted_report(tmp_path: Path) -> None:
    persist_analysis(_result(), root=tmp_path)
    app = BrowserApp(offline=True, root=tmp_path)
    async with app.run_test(size=(120, 32)) as pilot:
        assert app.tab == "local"
        assert app._items
        await pilot.press("enter")
        assert isinstance(app.return_value, OpenReview)
        assert app.return_value.result.pr.title == "fees"


@pytest.mark.asyncio
async def test_inbox_row_does_not_analyze(tmp_path: Path) -> None:
    BrowserCatalog(tmp_path).put_inbox(
        "authored",
        [
            {
                "repo": "acme/pay",
                "number": 99,
                "title": "remote only",
                "tab": "authored",
                "author": "me",
                "updated_at": "now",
                "latest_rev": "fff",
                "ci_summary": "",
            }
        ],
    )
    app = BrowserApp(offline=True, root=tmp_path)
    async with app.run_test(size=(120, 32)) as pilot:
        await pilot.press("2")
        assert app.tab == "authored"
        await pilot.press("enter")
        assert app.return_value is None
        assert "does not clone" in app._status


@pytest.mark.asyncio
async def test_inbox_enter_opens_unanalyzed_review(tmp_path: Path) -> None:
    BrowserCatalog(tmp_path).put_inbox(
        "authored",
        [
            {
                "repo": "acme/pay",
                "number": 99,
                "title": "remote only",
                "tab": "authored",
                "author": "me",
                "updated_at": "now",
                "latest_rev": "fff",
                "ci_summary": "",
            }
        ],
    )
    app = BrowserApp(offline=True, root=tmp_path)
    async with app.run_test(size=(120, 32)) as pilot:
        await pilot.press("2")
        assert app.tab == "authored"
        assert app._items
        assert not app._items[0].has_local_report
        app.offline = False
        await pilot.press("enter")
        assert isinstance(app.return_value, OpenInbox)
        assert app.return_value.repo == "acme/pay"
        assert app.return_value.number == 99
        assert BrowserCatalog(tmp_path).list_entries() == []


@pytest.mark.asyncio
async def test_offline_refresh_does_not_leave_browser(tmp_path: Path) -> None:
    persist_analysis(_result(), root=tmp_path)
    app = BrowserApp(offline=True, root=tmp_path)
    async with app.run_test(size=(120, 32)) as pilot:
        await pilot.press("r")
        assert "offline" in app._status
        assert app.return_value is None


def test_browser_rows_group_reviews_under_repo() -> None:
    pay = [
        BrowserItem(repo="acme/pay", number=7, title="fees"),
        BrowserItem(repo="acme/pay", number=99, title="remote only"),
    ]
    web = BrowserItem(repo="acme/web", number=3, title="docs")
    rows = rows_from_items([*pay, web])
    kinds = [row.kind for row in rows]
    assert kinds == ["repo", "review", "review", "repo", "review"]
    assert rows[0].label.startswith("acme/pay")
    assert rows[0].has_children
    assert rows[1].item is not None
    assert rows[1].item.number == 7
    assert rows[1].parent_key == rows[0].node_key
    assert rows[2].last
    assert rows[3].label.startswith("acme/web")
    assert "#7" in rows[1].render()
    assert "acme/pay#7" not in rows[1].render()
    folded = visible_browser_rows(rows, {rows[0].node_key})
    assert [row.kind for row in folded] == ["repo", "repo", "review"]


@pytest.mark.asyncio
async def test_browser_repos_start_collapsed(tmp_path: Path) -> None:
    persist_analysis(_result(), root=tmp_path)
    persist_analysis(
        AnalysisResult(
            pr=PullRequest(
                number=8,
                title="other",
                body="",
                base_ref="main",
                head_ref="g",
                head_sha="defdefdefdef",
                additions=1,
                deletions=0,
                repo="acme/pay",
            ),
            changes=[LogicalChange(id="C1", title="other")],
        ),
        root=tmp_path,
    )
    app = BrowserApp(offline=True, root=tmp_path)
    async with app.run_test(size=(120, 32)) as pilot:
        assert [row.kind for row in app._visible] == ["repo"]
        assert app._visible[app._cursor].kind == "repo"
        assert "▶" in app._visible[0].render(collapsed=True)
        await pilot.press("space")
        assert [row.kind for row in app._visible] == ["repo", "review", "review"]
        await pilot.press("space")
        assert [row.kind for row in app._visible] == ["repo"]


def test_filter_disabled_hides_repo() -> None:
    items = [
        BrowserItem(repo="acme/pay", number=1, title="fees"),
        BrowserItem(repo="acme/web", number=2, title="docs"),
    ]
    hidden = filter_disabled(items, {"acme/pay"})
    assert [item.repo for item in hidden] == ["acme/web"]


@pytest.mark.asyncio
async def test_repo_filter_persists_across_browser_sessions(tmp_path: Path) -> None:
    persist_analysis(_result(), root=tmp_path)
    persist_analysis(
        AnalysisResult(
            pr=PullRequest(
                number=3,
                title="docs",
                body="",
                base_ref="main",
                head_ref="g",
                head_sha="defdefdefdef",
                additions=1,
                deletions=0,
                repo="acme/web",
            ),
            changes=[LogicalChange(id="C1", title="docs")],
        ),
        root=tmp_path,
    )
    prefs = PrefsStore(tmp_path / "prefs")
    first = BrowserApp(offline=True, root=tmp_path, prefs=prefs)
    async with first.run_test(size=(120, 32)) as pilot:
        assert {item.repo for item in first._items} == {"acme/pay", "acme/web"}
        await pilot.press("f")
        assert isinstance(first.screen, RepoFilterDialog)
        assert first.screen._repos == ["acme/pay", "acme/web"]
        await pilot.press("space")
        await pilot.press("enter")
        assert {item.repo for item in first._items} == {"acme/web"}
        assert prefs.load_disabled_repos() == {"acme/pay"}
    second = BrowserApp(offline=True, root=tmp_path, prefs=prefs)
    async with second.run_test(size=(120, 32)):
        assert {item.repo for item in second._items} == {"acme/web"}
        assert [row.repo for row in second._visible if row.kind == "repo"] == ["acme/web"]


@pytest.mark.asyncio
async def test_browser_hides_closed_prs_until_toggled(tmp_path: Path) -> None:
    persist_analysis(_result(), root=tmp_path)
    closed = persist_analysis(
        AnalysisResult(
            pr=PullRequest(
                number=9,
                title="merged work",
                body="",
                base_ref="main",
                head_ref="g",
                head_sha="999999999999",
                additions=1,
                deletions=0,
                repo="acme/pay",
            ),
            changes=[LogicalChange(id="C1", title="merged work")],
        ),
        root=tmp_path,
    )
    catalog = BrowserCatalog(tmp_path)
    review_id = closed.review_id
    assert review_id is not None
    entry = catalog.get_entry(review_id)
    assert entry is not None
    catalog.put_entry(entry.model_copy(update={"pr_state": "merged"}))
    app = BrowserApp(offline=True, root=tmp_path)
    async with app.run_test(size=(120, 32)) as pilot:
        assert {item.number for item in app._items} == {7}
        assert "open PRs" in app._status
        await pilot.press("o")
        assert {item.number for item in app._items} == {7, 9}
        assert "all PRs" in app._status
