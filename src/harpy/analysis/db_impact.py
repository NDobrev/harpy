"""Static fallback for schema/migration changes. No diagrams — the agent decides those."""

from __future__ import annotations

import re
from pathlib import Path

from harpy.analysis.schema_view import schema_from_patch
from harpy.models import (
    AnalysisResult,
    DbChangeImpact,
    DdlFact,
    DiffHunk,
    FileCategory,
    SchemaColumn,
    SchemaSnapshot,
    SchemaTable,
)

_DDL = re.compile(
    r"""(?ix)
    (?:CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)(?P<create_table>[\w."]+)
    | (?:DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?)(?P<drop_table>[\w."]+)
    | (?:ALTER\s+TABLE\s+)(?P<alter_table>[\w."]+)
    | (?:addColumn\(\s*['"])(?P<add_col_table>[^'"]+)
    | (?:dropColumn\(\s*['"])(?P<drop_col_table>[^'"]+)
    | (?:createTable\(\s*['"])(?P<knex_create>[^'"]+)
    | (?:dropTable\(\s*['"])(?P<knex_drop>[^'"]+)
    | (?:pgTable\(\s*['"])(?P<drizzle>[^'"]+)
    | (?:model\s+)(?P<prisma>\w+)
    """
)
_COLUMN = re.compile(
    r"""(?ix)
    ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<add>[\w"]+)
    | DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(?P<drop>[\w"]+)
    | RENAME\s+(?:COLUMN\s+)?(?P<rename>[\w"]+)
    | ALTER\s+COLUMN\s+(?P<alter>[\w"]+)
    """
)
_BREAKING_DDL = re.compile(
    r"""(?ix)
    DROP\s+TABLE | DROP\s+COLUMN | dropTable\s*\( | dropColumn\s*\(
    | RENAME\s+COLUMN | ALTER\s+COLUMN\s+\w+\s+TYPE
    """
)


def looks_like_db(result: AnalysisResult) -> bool:
    if any(signal.migration for signal in result.signals):
        return True
    if any(facts.ddl for facts in result.file_facts):
        return True
    if any(_file_is_schema(file.path, file.category_scores) for file in result.files):
        return True
    return any(_has_ddl(hunk.patch) for hunk in result.hunks)


def extract_static_db_impacts(result: AnalysisResult) -> list[DbChangeImpact]:
    if not looks_like_db(result):
        return []
    seen: dict[tuple[str, str], DbChangeImpact] = {}
    fact_paths = {facts.path.replace("\\", "/") for facts in result.file_facts if facts.ddl}
    for facts in result.file_facts:
        for ddl in facts.ddl:
            operation, target = _from_ddl(ddl)
            if not target:
                continue
            _add_impact(
                seen,
                result,
                operation=operation,
                target=target,
                file_path=facts.path,
                hunk_id=_hunk_id_for(result, facts.path),
                breaking=operation in {"drop_table", "drop_column"},
                schema=_schema_from_ddl(ddl),
            )
    for hunk in result.hunks:
        if hunk.file_path.replace("\\", "/") in fact_paths:
            continue
        if not (_hunk_is_schema(result, hunk) or _has_ddl(hunk.patch)):
            continue
        breaking = bool(_BREAKING_DDL.search(hunk.patch))
        found = _objects_in(hunk.patch)
        if not found:
            found = [("other", Path(hunk.file_path).name)]
        for operation, target in found:
            _add_impact(
                seen,
                result,
                operation=operation,
                target=target,
                file_path=hunk.file_path,
                hunk_id=hunk.id,
                breaking=breaking,
                schema=schema_from_patch(hunk.patch, operation=operation, target=target),
            )
    return list(seen.values())


def _from_ddl(ddl: DdlFact) -> tuple[str, str]:
    operation = ddl.operation or "other"
    if ddl.column and operation != "add_table":
        return operation, f"{ddl.table}.{ddl.column}" if ddl.table else ddl.column
    return operation, ddl.table


def _schema_from_ddl(ddl: DdlFact) -> SchemaSnapshot:
    table_change = {
        "add_table": "add",
        "drop_table": "drop",
    }.get(ddl.operation, "alter")
    columns: list[SchemaColumn] = []
    if ddl.column:
        columns.append(
            SchemaColumn(
                name=ddl.column,
                type=ddl.col_type,
                nullable=True if ddl.nullable is None else ddl.nullable,
                fk=ddl.fk_table,
                fk_column=ddl.fk_column,
                change={
                    "add_column": "add",
                    "drop_column": "drop",
                    "add_table": "add",
                }.get(ddl.operation, "alter"),
            )
        )
    return SchemaSnapshot(
        tables=[SchemaTable(name=ddl.table, change=table_change, columns=columns)]
    )


def _hunk_id_for(result: AnalysisResult, path: str) -> str:
    for hunk in result.hunks:
        if hunk.file_path.replace("\\", "/") == path.replace("\\", "/"):
            return hunk.id
    return ""


def _add_impact(
    seen: dict[tuple[str, str], DbChangeImpact],
    result: AnalysisResult,
    *,
    operation: str,
    target: str,
    file_path: str,
    hunk_id: str,
    breaking: bool,
    schema: SchemaSnapshot,
) -> None:
    key = (operation, target)
    dropped = breaking or operation in {"drop_table", "drop_column"}
    if key in seen:
        if dropped:
            seen[key].breaking = True
            seen[key].breaking_reason = "a table or column was dropped or rewritten in the diff"
        if file_path and file_path not in seen[key].files:
            seen[key].files.append(file_path)
        return
    seen[key] = DbChangeImpact(
        change_id=_change_id_for(result, hunk_id),
        operation=operation,
        target=target,
        summary=f"{operation} {target}".strip(),
        objects=[target],
        schema=schema,
        impact="Static extraction only — wait for semantic analysis for behavior and diagrams.",
        breaking=dropped,
        breaking_reason=(
            "a table or column was dropped or rewritten in the diff" if dropped else ""
        ),
        files=[file_path] if file_path else [],
    )


def _file_is_schema(path: str, scores: dict[str, float]) -> bool:
    if scores.get(FileCategory.MIGRATION, 0.0) >= 0.5:
        return True
    lower = path.replace("\\", "/").lower()
    name = Path(lower).name
    return (
        lower.endswith(".sql")
        or name in {"schema.prisma", "schema.rb"}
        or "/migrations/" in lower
        or "/alembic/" in lower
        or "/db/migrate/" in lower
    )


def _hunk_is_schema(result: AnalysisResult, hunk: DiffHunk) -> bool:
    for signal in result.signals:
        if signal.hunk_id == hunk.id and signal.migration:
            return True
    for file in result.files:
        if file.path == hunk.file_path and _file_is_schema(file.path, file.category_scores):
            return True
    return False


def _has_ddl(patch: str) -> bool:
    return bool(_DDL.search(patch))


def _objects_in(patch: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    matches = list(_DDL.finditer(patch))
    for index, match in enumerate(matches):
        if match.group("create_table") or match.group("knex_create") or match.group("drizzle"):
            table = _ident(
                match.group("create_table") or match.group("knex_create") or match.group("drizzle")
            )
            found.append(("add_table", table))
        elif match.group("drop_table") or match.group("knex_drop"):
            table = _ident(match.group("drop_table") or match.group("knex_drop"))
            found.append(("drop_table", table))
        elif match.group("add_col_table"):
            found.append(("add_column", _ident(match.group("add_col_table"))))
        elif match.group("drop_col_table"):
            found.append(("drop_column", _ident(match.group("drop_col_table"))))
        elif match.group("prisma"):
            found.append(("other", _ident(match.group("prisma"))))
        elif match.group("alter_table"):
            table = _ident(match.group("alter_table"))
            stop = matches[index + 1].start() if index + 1 < len(matches) else len(patch)
            statement = patch[match.start() : stop]
            columns = list(_COLUMN.finditer(statement))
            if not columns:
                found.append(("alter", table))
                continue
            for column in columns:
                name = _ident(
                    column.group("add")
                    or column.group("drop")
                    or column.group("rename")
                    or column.group("alter")
                    or ""
                )
                if column.group("add"):
                    found.append(("add_column", f"{table}.{name}" if name else table))
                elif column.group("drop"):
                    found.append(("drop_column", f"{table}.{name}" if name else table))
                elif column.group("rename"):
                    found.append(("rename", f"{table}.{name}" if name else table))
                else:
                    found.append(("alter_column", f"{table}.{name}" if name else table))
    return found


def _ident(raw: str) -> str:
    return raw.strip().strip("\"'")


def _change_id_for(result: AnalysisResult, hunk_id: str) -> str:
    for change in result.changes:
        if hunk_id in (change.hunks or change.hunk_ids):
            return change.id
    return ""
