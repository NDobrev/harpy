"""Unified rows for the API/DB impact pane."""

from __future__ import annotations

from dataclasses import dataclass

from rich.markup import escape

from harpy.models import (
    AnalysisResult,
    ApiDiagram,
    ApiEndpointImpact,
    DbChangeImpact,
    LogicalChange,
)


@dataclass(frozen=True)
class ImpactEntry:
    kind: str
    api: ApiEndpointImpact | None = None
    db: DbChangeImpact | None = None

    @property
    def breaking(self) -> bool:
        if self.api is not None:
            return self.api.breaking
        return bool(self.db is not None and self.db.breaking)

    @property
    def diagrams(self) -> list[ApiDiagram]:
        item = self.api or self.db
        return item.diagrams if item is not None else []

    @property
    def files(self) -> list[str]:
        item = self.api or self.db
        return list(item.files) if item is not None else []

    @property
    def business_logic(self) -> bool:
        item = self.api or self.db
        return bool(item is not None and item.business_logic)

    @property
    def business_logic_why(self) -> str:
        item = self.api or self.db
        return item.business_logic_why if item is not None else ""

    @property
    def security(self) -> bool:
        item = self.api or self.db
        return bool(item is not None and item.security)

    @property
    def security_why(self) -> str:
        item = self.api or self.db
        return item.security_why if item is not None else ""


@dataclass
class ImpactDisplayRow:
    kind: str
    impact_index: int
    label: str
    file_path: str | None = None
    has_children: bool = False
    last: bool = False
    node_key: str = ""
    parent_key: str | None = None
    tone: str = "api"

    def render(self, *, collapsed: bool = False) -> str:
        if self.kind == "impact":
            marker = ""
            if self.has_children:
                marker = "▶ " if collapsed else "▼ "
            return f"{marker}{self.label}"
        branch = "└─ " if self.last else "├─ "
        return f"    {branch}{escape(self.label)}"


def entries_from_result(result: AnalysisResult) -> list[ImpactEntry]:
    return [
        *[ImpactEntry(kind="api", api=item) for item in result.api_impacts],
        *[ImpactEntry(kind="db", db=item) for item in result.db_impacts],
    ]


def rows_from_entries(entries: list[ImpactEntry]) -> list[ImpactDisplayRow]:
    rows: list[ImpactDisplayRow] = []
    for index, item in enumerate(entries):
        key = f"impact:{index}"
        files = item.files
        tone = impact_tone(item)
        rows.append(
            ImpactDisplayRow(
                kind="impact",
                impact_index=index,
                label=_impact_label(item),
                has_children=bool(files),
                node_key=key,
                tone=tone,
            )
        )
        for file_index, path in enumerate(files):
            rows.append(
                ImpactDisplayRow(
                    kind="file",
                    impact_index=index,
                    label=path,
                    file_path=path,
                    last=file_index == len(files) - 1,
                    parent_key=key,
                    tone=tone,
                )
            )
    return rows


def visible_impact_rows(
    rows: list[ImpactDisplayRow], collapsed: set[str]
) -> list[ImpactDisplayRow]:
    hidden: set[str] = set()
    visible: list[ImpactDisplayRow] = []
    for row in rows:
        if row.parent_key and row.parent_key in collapsed:
            hidden.add(row.node_key)
            continue
        if row.parent_key and row.parent_key in hidden:
            continue
        visible.append(row)
    return visible


def change_for_impact(
    result: AnalysisResult,
    item: ImpactEntry,
    file_path: str | None = None,
) -> LogicalChange | None:
    payload = item.api or item.db
    change_id = payload.change_id if payload is not None else ""
    if change_id:
        for change in result.changes:
            if change.id == change_id:
                return change
    if file_path:
        for change in result.changes:
            if file_path in change.files:
                return change
        for change in result.changes:
            hunk_ids = set(change.hunks or change.hunk_ids)
            if any(hunk.id in hunk_ids and hunk.file_path == file_path for hunk in result.hunks):
                return change
        return LogicalChange(id="", title=file_path, files=[file_path])
    return None


def impact_tone(item: ImpactEntry) -> str:
    if item.breaking:
        return "breaking"
    if item.security:
        return "sec"
    if item.business_logic:
        return "bl"
    if item.kind == "db" or item.db is not None:
        return "db"
    return "api"


def row_classes(row: ImpactDisplayRow) -> str:
    extra = "impact-file" if row.kind == "file" else "impact-item"
    return f"tree-row tree-selectable impact-{row.tone} {extra}"


def _mark(style: str, text: str) -> str:
    return f"[{style}]{escape(text)}[/]"


def _impact_label(item: ImpactEntry) -> str:
    warn = f"{_mark('bold red', '⚠')} " if item.breaking else "  "
    tags: list[str] = []
    if item.business_logic:
        tags.append(_mark("bold yellow", "BL"))
    if item.security:
        tags.append(_mark("bold #d946ef", "SEC"))
    suffix = f"  ·  {' '.join(tags)}" if tags else ""
    if item.api is not None:
        rest = f"{item.api.method} {item.api.path}".strip()
        rest = rest if item.api.path or item.api.method else item.api.summary
        rest = rest.strip() or "(unnamed endpoint)"
        kind = _mark("bold cyan", "API")
        summary = item.api.summary
        target_plain = f"API  {rest}"
    elif item.db is not None:
        rest = f"{item.db.operation} {item.db.target}".strip() or item.db.summary
        rest = rest.strip() or "(unnamed schema change)"
        kind = _mark("bold #7dd3fc", "DB")
        summary = item.db.summary
        target_plain = f"DB   {rest}"
    else:
        return f"{warn}(empty)"
    head = f"{warn}{kind}  {escape(rest)}{suffix}"
    if summary and summary != target_plain and summary != rest:
        return f"{head}\n  {escape(summary)}"
    return head
