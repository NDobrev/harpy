"""Persist analyses and assemble browser listings. No TUI."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from harpy.analysis.workflows.session import OpenReview
from harpy.github.inbox import InboxPage, InboxRow, query_inbox, refresh_heads
from harpy.models import AnalysisReport, AnalysisResult, BrowserItem, Freshness, ReportProvenance
from harpy.storage.catalog import BrowserCatalog, freshness_for
from harpy.storage.db import ReviewStore
from harpy.storage.paths import data_home

BROWSER_TABS = ("local", "authored", "assigned", "review-requested", "tracked")


def persist_analysis(result: AnalysisResult, *, root: Path | None = None) -> BrowserItem:
    store = ReviewStore(root or data_home())
    try:
        report = AnalysisReport(
            id=uuid4(),
            snapshot_id=uuid4(),
            provenance=ReportProvenance(run_id=uuid4()),
        )
        store.put_report(report)
        review_id = _reuse_review_id(store.catalog, result) or uuid4()
        item = BrowserItem(
            review_id=review_id,
            report_id=report.id,
            tab="local",
            repo=result.pr.repo,
            number=result.pr.number or None,
            title=result.pr.title,
            source="github" if result.pr.repo else "local",
            analyzed_rev=(result.pr.head_sha or "")[:12],
            latest_rev=(result.pr.head_sha or "")[:12],
            analyzed_at=_clock(),
            completeness=_completeness(result),
            review_progress=f"0/{len(result.changes)}",
            freshness=Freshness.CURRENT if result.pr.head_sha else Freshness.UNKNOWN,
            has_local_report=True,
        )
        if item.number == 0:
            item = item.model_copy(update={"number": None})
        stored = store.catalog.put_entry(item, result)
        session = store.catalog.get_session(review_id)
        if session and session.get("review_progress"):
            stored = store.catalog.put_entry(
                stored.model_copy(update={"review_progress": str(session["review_progress"])})
            )
        return stored
    finally:
        store.close()


def load_analysis(review_id: UUID, *, root: Path | None = None) -> AnalysisResult | None:
    catalog = BrowserCatalog(root or data_home())
    result = catalog.get_result(review_id)
    if result is None:
        return None
    return _without_expired_worktree(result)


def load_analysis_by_report(report_id: UUID, *, root: Path | None = None) -> AnalysisResult | None:
    opened = load_open_review_by_report(report_id, root=root)
    return opened.result if opened else None


def load_open_review(review_id: UUID, *, root: Path | None = None) -> OpenReview | None:
    result = load_analysis(review_id, root=root)
    if result is None:
        return None
    return OpenReview(result=result, review_id=review_id)


def load_open_review_by_report(report_id: UUID, *, root: Path | None = None) -> OpenReview | None:
    catalog = BrowserCatalog(root or data_home())
    for item in catalog.list_entries():
        if item.report_id == report_id and item.review_id is not None:
            return load_open_review(item.review_id, root=root)
    return None


def list_browser(
    tab: str = "local",
    *,
    offline: bool = False,
    root: Path | None = None,
    runner: object | None = None,
    refresh_remote: bool = False,
) -> list[BrowserItem]:
    if tab not in BROWSER_TABS:
        tab = "local"
    catalog = BrowserCatalog(root or data_home())
    local = catalog.list_entries()
    if tab == "local":
        return [_with_freshness(item) for item in local]
    pages = {
        name: _inbox_page(
            name, offline=offline, catalog=catalog, runner=runner, refresh_remote=refresh_remote
        )
        for name in ("authored", "assigned", "review-requested")
    }
    if tab in pages:
        return _merge(local, pages[tab], tab=tab)
    tracked = _dedupe([*_flatten(pages), *local])
    return tracked


def history_for(reference: str, *, root: Path | None = None) -> list[BrowserItem]:
    items = list_browser("local", offline=True, root=root, refresh_remote=False)
    needle = reference.strip().lower()
    if needle.startswith("#"):
        needle = needle[1:]
    matched: list[BrowserItem] = []
    for item in items:
        hay = {
            str(item.review_id or ""),
            str(item.report_id or ""),
            str(item.number or ""),
            item.repo.lower(),
            f"{item.repo}#{item.number}".lower(),
            item.title.lower(),
        }
        if needle in hay or any(needle in token for token in hay if token):
            matched.append(item)
    return matched


def _inbox_page(
    tab: str,
    *,
    offline: bool,
    catalog: BrowserCatalog,
    runner: object | None,
    refresh_remote: bool,
) -> list[BrowserItem]:
    cached_rows, cached_at, cached_error, cached_trunc = catalog.get_inbox(tab)
    cached = InboxPage(
        rows=[_inbox_row(row) for row in cached_rows if _inbox_kwargs(row)],
        error=cached_error,
        fetched_at=cached_at,
        from_cache=True,
        truncated=cached_trunc,
    )
    page = query_inbox(tab, offline=offline, runner=runner, cached=cached)  # type: ignore[arg-type]
    rows = page.rows
    if refresh_remote and not offline and not page.error:
        prior = {(row.repo, row.number): row for row in cached.rows}
        rows = refresh_heads(rows, runner=runner, cached_heads=prior)  # type: ignore[arg-type]
    if not offline:
        catalog.put_inbox(
            tab,
            [_row_payload(row) for row in rows],
            error=page.error,
            truncated=page.truncated or cached.truncated,
        )
    error = page.error or cached_error
    truncated = page.truncated or cached.truncated
    fetched = page.fetched_at or cached_at
    items = [
        BrowserItem(
            tab=tab,
            repo=row.repo,
            number=row.number,
            title=row.title,
            author=row.author,
            source="github",
            latest_rev=(row.latest_rev or "")[:12],
            updated_at=row.updated_at,
            ci_summary=row.ci_summary,
            query_error=error,
            truncated=truncated,
            cached_at=fetched,
            freshness=Freshness.UNKNOWN,
        )
        for row in rows
    ]
    if not items and error:
        return [
            BrowserItem(
                tab=tab,
                query_error=error,
                cached_at=fetched,
                truncated=truncated,
            )
        ]
    return items


def _merge(local: list[BrowserItem], remote: list[BrowserItem], *, tab: str) -> list[BrowserItem]:
    by_key = {_key(item): item for item in local}
    merged: list[BrowserItem] = []
    for item in remote:
        if item.number is None and not item.repo and item.query_error:
            merged.append(item)
            continue
        found = by_key.get(_key(item))
        if found is None:
            merged.append(item.model_copy(update={"tab": tab}))
            continue
        latest = item.latest_rev or found.latest_rev
        merged.append(
            found.model_copy(
                update={
                    "tab": tab,
                    "author": item.author or found.author,
                    "latest_rev": latest,
                    "updated_at": item.updated_at or found.updated_at,
                    "ci_summary": item.ci_summary or found.ci_summary,
                    "query_error": item.query_error,
                    "truncated": item.truncated,
                    "cached_at": item.cached_at,
                    "freshness": freshness_for(found.analyzed_rev, latest),
                    "has_local_report": True,
                }
            )
        )
    return merged


def _dedupe(items: list[BrowserItem]) -> list[BrowserItem]:
    seen: dict[str, BrowserItem] = {}
    for item in items:
        key = _key(item)
        current = seen.get(key)
        if current is None:
            seen[key] = item.model_copy(update={"tab": "tracked"})
            continue
        if item.has_local_report and not current.has_local_report:
            seen[key] = item.model_copy(
                update={
                    "tab": "tracked",
                    "freshness": freshness_for(
                        item.analyzed_rev, item.latest_rev or current.latest_rev
                    ),
                }
            )
            continue
        latest = item.latest_rev or current.latest_rev
        seen[key] = current.model_copy(
            update={
                "latest_rev": latest,
                "freshness": freshness_for(current.analyzed_rev, latest),
                "author": current.author or item.author,
                "ci_summary": current.ci_summary or item.ci_summary,
            }
        )
    return list(seen.values())


def _flatten(pages: dict[str, list[BrowserItem]]) -> list[BrowserItem]:
    rows: list[BrowserItem] = []
    for items in pages.values():
        rows.extend(item for item in items if item.number is not None)
    return rows


def _key(item: BrowserItem) -> str:
    if item.repo and item.number is not None:
        return f"{item.repo}#{item.number}"
    return str(item.review_id or item.title)


def _with_freshness(item: BrowserItem) -> BrowserItem:
    return item.model_copy(update={"freshness": freshness_for(item.analyzed_rev, item.latest_rev)})


def _completeness(result: AnalysisResult) -> str:
    if result.scopes_run:
        return f"{len(result.scopes_run)} scopes"
    if result.semantic_available:
        return "semantic"
    if result.pending_semantic:
        return "static"
    return "static"


def _without_expired_worktree(result: AnalysisResult) -> AnalysisResult:
    path = result.workspace_path
    if path and Path(path).is_dir():
        return result
    banner = result.banner
    if path:
        note = "Worktree expired. Showing persisted analysis."
        banner = f"{banner}  ·  {note}" if banner else note
    return result.model_copy(update={"workspace_path": None, "banner": banner})


def _reuse_review_id(catalog: BrowserCatalog, result: AnalysisResult) -> UUID | None:
    for entry in catalog.list_entries():
        if result.pr.repo and entry.repo == result.pr.repo and entry.number == result.pr.number:
            return entry.review_id
        if (
            not result.pr.repo
            and entry.title == result.pr.title
            and entry.analyzed_rev == (result.pr.head_sha or "")[:12]
        ):
            return entry.review_id
    return None


def _clock() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _row_payload(row: InboxRow) -> dict[str, object]:
    return {
        "repo": row.repo,
        "number": row.number,
        "title": row.title,
        "tab": row.tab,
        "author": row.author,
        "updated_at": row.updated_at,
        "latest_rev": row.latest_rev,
        "ci_summary": row.ci_summary,
    }


def _inbox_kwargs(row: dict[str, object]) -> bool:
    return bool(row.get("repo") and row.get("number") is not None)


def _inbox_row(row: dict[str, object]) -> InboxRow:
    return InboxRow(
        repo=str(row.get("repo") or ""),
        number=int(str(row["number"])),
        title=str(row.get("title") or ""),
        tab=str(row.get("tab") or ""),
        author=str(row.get("author") or ""),
        updated_at=str(row.get("updated_at") or ""),
        latest_rev=str(row.get("latest_rev") or ""),
        ci_summary=str(row.get("ci_summary") or ""),
    )
