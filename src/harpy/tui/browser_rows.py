"""Repo-grouped rows for the analysis browser."""

from __future__ import annotations

from dataclasses import dataclass

from harpy.models import BrowserItem


@dataclass
class BrowserDisplayRow:
    kind: str
    label: str
    item: BrowserItem | None = None
    repo: str = ""
    has_children: bool = False
    last: bool = False
    node_key: str = ""
    parent_key: str | None = None

    def render(self, *, selected: bool = False, collapsed: bool = False) -> str:
        cursor = "▸ " if selected else "  "
        if self.kind == "repo":
            marker = "▶ " if collapsed else "▼ "
            return f"{cursor}{marker}{self.label}"
        branch = "└─ " if self.last else "├─ "
        return f"{cursor}  {branch}{self.label}"


def rows_from_items(items: list[BrowserItem]) -> list[BrowserDisplayRow]:
    groups: dict[str, list[BrowserItem]] = {}
    order: list[str] = []
    for item in items:
        repo = repo_key(item)
        if repo not in groups:
            order.append(repo)
            groups[repo] = []
        groups[repo].append(item)
    rows: list[BrowserDisplayRow] = []
    for repo in order:
        children = groups[repo]
        node_key = f"repo:{repo}"
        count = len(children)
        rows.append(
            BrowserDisplayRow(
                kind="repo",
                label=f"{repo}  {count} review{'s' if count != 1 else ''}",
                repo=repo,
                has_children=True,
                node_key=node_key,
            )
        )
        for index, item in enumerate(children):
            rows.append(
                BrowserDisplayRow(
                    kind="review",
                    label=_review_label(item),
                    item=item,
                    repo=repo,
                    last=index == count - 1,
                    node_key=item_key(item),
                    parent_key=node_key,
                )
            )
    return rows


def visible_browser_rows(
    rows: list[BrowserDisplayRow], collapsed: set[str]
) -> list[BrowserDisplayRow]:
    visible: list[BrowserDisplayRow] = []
    for row in rows:
        if row.parent_key and row.parent_key in collapsed:
            continue
        visible.append(row)
    return visible


def item_key(item: BrowserItem) -> str:
    if item.repo and item.number is not None:
        return f"{item.repo}#{item.number}"
    return str(item.review_id or item.title)


def repo_key(item: BrowserItem) -> str:
    if item.repo:
        return item.repo
    if item.query_error and item.number is None:
        return "(inbox)"
    return item.source or "(local)"


def known_repos(items: list[BrowserItem]) -> list[str]:
    names: list[str] = []
    for item in items:
        if item.repo and item.repo not in names:
            names.append(item.repo)
    return names


def filter_disabled(items: list[BrowserItem], disabled: set[str]) -> list[BrowserItem]:
    return [item for item in items if not item.repo or item.repo not in disabled]


def _review_label(item: BrowserItem) -> str:
    number = f"#{item.number}  " if item.number is not None else ""
    title = item.title or "(untitled)"
    author = f" · {item.author}" if item.author else ""
    badge = item.freshness.value.replace("_", " ")
    progress = item.review_progress or item.completeness or "no local report"
    rev = item.analyzed_rev or "—"
    latest = item.latest_rev or "—"
    ci = f" · {item.ci_summary}" if item.ci_summary else ""
    return f"{number}{title}{author}\n    analyzed {rev}  latest {latest}  {badge}  {progress}{ci}"
