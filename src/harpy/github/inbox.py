"""GitHub inbox queries. Metadata only; never starts analysis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from harpy.proc import ProcResult, run

InboxRunner = Callable[..., ProcResult]

TABS = ("authored", "assigned", "review-requested")
SEARCH = {
    "authored": "author:@me",
    "assigned": "assignee:@me",
    "review-requested": "review-requested:@me",
}
SEARCH_FIELDS = "number,title,repository,author,updatedAt,state"
INBOX_LIMIT = 20


@dataclass(frozen=True)
class InboxRow:
    repo: str
    number: int
    title: str
    tab: str
    author: str = ""
    updated_at: str = ""
    latest_rev: str = ""
    ci_summary: str = ""
    state: str = ""


@dataclass(frozen=True)
class InboxPage:
    rows: list[InboxRow] = field(default_factory=list)
    error: str = ""
    fetched_at: str = ""
    from_cache: bool = False
    truncated: bool = False


def query_inbox(
    tab: str,
    *,
    offline: bool = False,
    open_only: bool = True,
    runner: InboxRunner | None = None,
    cached: InboxPage | None = None,
) -> InboxPage:
    if tab not in SEARCH:
        return InboxPage(error="unknown inbox tab")
    if offline:
        prior = cached or InboxPage()
        return InboxPage(
            rows=list(prior.rows),
            error=prior.error,
            fetched_at=prior.fetched_at,
            from_cache=True,
            truncated=prior.truncated,
        )
    execute = runner or run
    query = SEARCH[tab]
    if open_only:
        query = f"{query} state:open"
    result = execute(
        ["gh", "search", "prs", query, "--limit", str(INBOX_LIMIT), "--json", SEARCH_FIELDS],
        timeout=20,
    )
    if not result.ok:
        prior = cached or InboxPage()
        reason = result.stderr.strip() or f"gh search failed ({result.returncode})"
        return InboxPage(
            rows=list(prior.rows),
            error=reason,
            fetched_at=prior.fetched_at,
            from_cache=True,
            truncated=prior.truncated,
        )
    rows = parse_inbox(result.stdout, tab=tab)
    return InboxPage(rows=rows, truncated=len(rows) >= INBOX_LIMIT)


def parse_inbox(payload: str, *, tab: str) -> list[InboxRow]:
    import json

    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    rows: list[InboxRow] = []
    seen: set[tuple[str, int]] = set()
    for raw in loaded:
        if not isinstance(raw, dict):
            continue
        repo = _repo(raw.get("repository"))
        number = raw.get("number")
        if not repo or not isinstance(number, int):
            continue
        key = (repo, number)
        if key in seen:
            continue
        seen.add(key)
        author = raw.get("author")
        login = ""
        if isinstance(author, dict):
            login = str(author.get("login") or "")
        rows.append(
            InboxRow(
                repo=repo,
                number=number,
                title=str(raw.get("title") or ""),
                tab=tab,
                author=login,
                updated_at=str(raw.get("updatedAt") or ""),
                state=str(raw.get("state") or "").lower(),
            )
        )
    return rows


def refresh_heads(
    rows: list[InboxRow],
    *,
    runner: InboxRunner | None = None,
    cached_heads: dict[tuple[str, int], InboxRow] | None = None,
) -> list[InboxRow]:
    execute = runner or run
    prior = cached_heads or {}
    updated: list[InboxRow] = []
    for row in rows:
        key = (row.repo, row.number)
        result = execute(
            [
                "gh",
                "pr",
                "view",
                str(row.number),
                "--repo",
                row.repo,
                "--json",
                "headRefOid,statusCheckRollup,state,mergedAt",
            ],
            timeout=20,
        )
        if not result.ok:
            updated.append(prior.get(key, row))
            continue
        head, ci, state = parse_pr_meta(result.stdout)
        updated.append(
            InboxRow(
                repo=row.repo,
                number=row.number,
                title=row.title,
                tab=row.tab,
                author=row.author,
                updated_at=row.updated_at,
                latest_rev=head or row.latest_rev,
                ci_summary=ci or row.ci_summary,
                state=state or row.state,
            )
        )
    return updated


def parse_pr_meta(payload: str) -> tuple[str, str, str]:
    import json

    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError:
        return "", "", ""
    if not isinstance(loaded, dict):
        return "", "", ""
    head = str(loaded.get("headRefOid") or "")
    state = str(loaded.get("state") or "").lower()
    if loaded.get("mergedAt") or loaded.get("merged") is True:
        state = "merged"
    return head, _ci_summary(loaded.get("statusCheckRollup")), state


def _repo(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    named = value.get("nameWithOwner")
    if isinstance(named, str) and named:
        return named
    name = str(value.get("name") or "")
    owner = value.get("owner")
    login = owner.get("login") if isinstance(owner, dict) else ""
    if login and name:
        return f"{login}/{name}"
    return ""


def _ci_summary(value: object) -> str:
    if not isinstance(value, list) or not value:
        return ""
    failed = 0
    pending = 0
    passed = 0
    for item in value:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state") or item.get("conclusion") or "").upper()
        if state in {"FAILURE", "ERROR", "FAILED"}:
            failed += 1
        elif state in {"PENDING", "QUEUED", "IN_PROGRESS"}:
            pending += 1
        elif state in {"SUCCESS", "NEUTRAL"}:
            passed += 1
    if failed:
        return f"{failed} failing"
    if pending:
        return f"{pending} pending"
    if passed:
        return f"{passed} passing"
    return ""
