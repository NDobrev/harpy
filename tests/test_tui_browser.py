from __future__ import annotations

from pathlib import Path

import pytest

from harpy.analysis.workflows.browser import persist_analysis
from harpy.analysis.workflows.session import OpenInbox, OpenReview
from harpy.models import AnalysisResult, LogicalChange, PullRequest
from harpy.storage.catalog import BrowserCatalog
from harpy.tui.screens.browser import BrowserApp


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
