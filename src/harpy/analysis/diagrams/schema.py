"""ASCII schema visualizer. Terminal boxes, not mermaid source."""

from __future__ import annotations

import re
from collections import defaultdict

from harpy.models import (
    DiagramHit,
    DiagramSpan,
    RenderedDiagram,
    SchemaColumn,
    SchemaRelation,
    SchemaSnapshot,
    SchemaTable,
)

_COL_MARK = {"add": "+", "drop": "-", "alter": "~"}
_TABLE_BADGE = {"add": "NEW", "drop": "DROPPED", "alter": "ALTERED"}
_SKIP_COL = re.compile(r"^(PRIMARY|UNIQUE|CONSTRAINT|CHECK|FOREIGN|INDEX)\b", re.I)


def merge_snapshots(snapshots: list[SchemaSnapshot]) -> SchemaSnapshot:
    tables: dict[str, SchemaTable] = {}
    relations: list[SchemaRelation] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for snapshot in snapshots:
        for table in snapshot.tables:
            existing = tables.get(table.name)
            if existing is None:
                tables[table.name] = table.model_copy(deep=True)
                continue
            columns = {column.name: column for column in existing.columns}
            for column in table.columns:
                columns[column.name] = column
            existing.columns = list(columns.values())
            if table.change and not existing.change:
                existing.change = table.change
        for relation in snapshot.relations:
            key = (
                relation.from_table,
                relation.to_table,
                relation.from_column,
                relation.to_column,
                relation.label,
                relation.change,
            )
            if key in seen:
                continue
            seen.add(key)
            relations.append(relation)
    return SchemaSnapshot(tables=list(tables.values()), relations=relations)


def render_schema(
    snapshot: SchemaSnapshot,
    *,
    highlight: str = "",
    width: int = 40,
    title: str = "SCHEMA",
    show_legend: bool = True,
) -> str:
    lines, _spans = _draw_schema(
        snapshot, highlight=highlight, width=width, title=title, show_legend=show_legend
    )
    return "\n".join(lines)


def has_structural_change(snapshot: SchemaSnapshot) -> bool:
    if any(table.change for table in snapshot.tables):
        return True
    if any(column.change for table in snapshot.tables for column in table.columns):
        return True
    return any(relation.change for relation in snapshot.relations)


def split_before_after(snapshot: SchemaSnapshot) -> tuple[SchemaSnapshot, SchemaSnapshot]:
    old_tables: list[SchemaTable] = []
    new_tables: list[SchemaTable] = []
    for table in snapshot.tables:
        if table.change == "add":
            new_tables.append(table)
            continue
        if table.change == "drop":
            old_tables.append(table)
            continue
        old_columns = [_old_column(column) for column in table.columns if column.change != "add"]
        new_columns = [column for column in table.columns if column.change != "drop"]
        if old_columns:
            old_tables.append(SchemaTable(name=table.name, change="", columns=old_columns))
        if new_columns:
            new_tables.append(
                SchemaTable(
                    name=table.name,
                    change=(
                        "alter"
                        if table.change == "alter" or any(column.change for column in new_columns)
                        else ""
                    ),
                    columns=new_columns,
                )
            )
    needed = {table.name for table in old_tables + new_tables}
    for relation in snapshot.relations:
        if relation.change:
            needed.add(relation.from_table)
            needed.add(relation.to_table)
    by_name = {table.name: table for table in snapshot.tables}
    for name in needed:
        if name not in {table.name for table in old_tables} and name not in {
            table.name for table in new_tables
        }:
            neighbor = by_name.get(name)
            if neighbor is None:
                neighbor = SchemaTable(name=name)
            if any(rel.change == "drop" for rel in snapshot.relations if _rel_touches(rel, name)):
                old_tables.append(SchemaTable(name=name, columns=neighbor.columns))
            if any(rel.change == "add" for rel in snapshot.relations if _rel_touches(rel, name)):
                new_tables.append(SchemaTable(name=name, columns=neighbor.columns))
    old = SchemaSnapshot(
        tables=old_tables,
        relations=[rel for rel in snapshot.relations if rel.change in {"drop", "alter"}],
    )
    new = SchemaSnapshot(
        tables=new_tables,
        relations=[rel for rel in snapshot.relations if rel.change in {"add", "alter"}],
    )
    return old, new


def render_before_after(
    snapshot: SchemaSnapshot,
    *,
    highlight: str = "",
    width: int = 40,
) -> str:
    lines, _spans = _draw_before_after(snapshot, highlight=highlight, width=width)
    return "\n".join(lines).rstrip()


def schema_picture(
    snapshot: SchemaSnapshot,
    *,
    highlight: str = "",
    width: int = 40,
) -> RenderedDiagram:
    if has_structural_change(snapshot):
        lines, spans = _draw_before_after(snapshot, highlight=highlight, width=width)
        text = "\n".join(lines).rstrip()
        lines = text.splitlines()
        spans = [span for span in spans if span.row < len(lines)]
    else:
        lines, spans = _draw_schema(snapshot, highlight=highlight, width=width)
    return RenderedDiagram(
        title="SCHEMA",
        kind="schema",
        lines=lines,
        hits=_hits_from_tables(lines, snapshot.tables),
        spans=spans,
    )


def _draw_schema(
    snapshot: SchemaSnapshot,
    *,
    highlight: str = "",
    width: int = 40,
    title: str = "SCHEMA",
    show_legend: bool = True,
) -> tuple[list[str], list[DiagramSpan]]:
    if not snapshot.tables:
        return [], []
    tables = _order_tables(snapshot.tables, snapshot.relations, highlight)
    inner = max(20, min(width, 48) - 2)
    lines = [title]
    if show_legend:
        lines.append("  + added   - dropped   ~ changed")
    lines.append("")
    spans: list[DiagramSpan] = []
    drawn = 0
    for table in tables:
        if drawn:
            connector, connector_spans = _connector_after(
                tables[drawn - 1], table, snapshot.relations
            )
            spans.extend(_shift_spans(connector_spans, len(lines)))
            lines.extend(connector)
            lines.append("")
        table_lines, table_spans = _render_table(table, inner=inner, highlight=highlight)
        spans.extend(_shift_spans(table_spans, len(lines)))
        lines.extend(table_lines)
        drawn += 1
    leftover, leftover_spans = _leftover_relations(tables, snapshot.relations)
    if leftover:
        lines.append("")
        lines.append("RELATIONS")
        spans.extend(_shift_spans(leftover_spans, len(lines)))
        lines.extend(leftover)
    return lines, spans


def _draw_before_after(
    snapshot: SchemaSnapshot,
    *,
    highlight: str = "",
    width: int = 40,
) -> tuple[list[str], list[DiagramSpan]]:
    old, new = split_before_after(snapshot)
    lines = ["SCHEMA", "  + added   - dropped   ~ changed", ""]
    spans: list[DiagramSpan] = []
    if old.tables:
        chunk, chunk_spans = _draw_schema(
            old, highlight=highlight, width=width, title="OLD", show_legend=False
        )
        spans.extend(_shift_spans(chunk_spans, len(lines)))
        lines.extend(chunk)
        lines.append("")
    if new.tables:
        chunk, chunk_spans = _draw_schema(
            new, highlight=highlight, width=width, title="NEW", show_legend=False
        )
        spans.extend(_shift_spans(chunk_spans, len(lines)))
        lines.extend(chunk)
        lines.append("")
    changed = [rel for rel in snapshot.relations if rel.change]
    if changed:
        lines.append("RELATIONS CHANGED")
        for relation in changed:
            line = f"  {_relation_change_line(relation)}"
            _add_span(spans, row=len(lines), col=0, width=len(line), tone=_tone(relation.change))
            lines.append(line)
    return lines, spans


def schema_from_patch(patch: str, *, operation: str, target: str) -> SchemaSnapshot:
    if operation == "drop_table":
        return SchemaSnapshot(tables=[SchemaTable(name=target, change="drop")])
    if operation == "add_table":
        columns = _create_columns(patch, target)
        created = SchemaTable(name=target, change="add", columns=columns)
        return SchemaSnapshot(
            tables=[created],
            relations=_relations_from_columns(target, columns, change="add"),
        )
    if operation in {"add_column", "drop_column", "alter_column", "rename"}:
        table_name, _, column_name = target.rpartition(".")
        table_name = table_name or target
        column_name = column_name or target
        change = {
            "add_column": "add",
            "drop_column": "drop",
            "alter_column": "alter",
            "rename": "alter",
        }[operation]
        parsed = _sql_column(_add_column_def(patch, column_name), change=change)
        col = parsed or SchemaColumn(
            name=column_name,
            type=_column_type(patch, column_name),
            change=change,
        )
        relations = _relations_from_columns(table_name, [col], change=change)
        return SchemaSnapshot(
            tables=[
                SchemaTable(
                    name=table_name,
                    change="alter",
                    columns=[col],
                )
            ],
            relations=relations,
        )
    return SchemaSnapshot()


def _old_column(column: SchemaColumn) -> SchemaColumn:
    if column.change != "alter" or not column.old_type:
        return column
    return column.model_copy(update={"type": column.old_type})


def _rel_touches(relation: SchemaRelation, name: str) -> bool:
    return relation.from_table == name or relation.to_table == name


def _relation_change_line(relation: SchemaRelation) -> str:
    mark = {"add": "+ ADDED", "drop": "- DROPPED", "alter": "~ CHANGED"}.get(
        relation.change, relation.change
    )
    left = relation.from_table
    if relation.from_column:
        left = f"{left}.{relation.from_column}"
    right = relation.to_table
    if relation.to_column:
        right = f"{right}.{relation.to_column}"
    label = f"  {relation.label}" if relation.label else ""
    return f"{mark}  {left} → {right}{label}"


def _create_columns(patch: str, table: str) -> list[SchemaColumn]:
    escaped = re.escape(table)
    match = re.search(
        rf"(?is)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{escaped}\s*\((?P<body>[^;]+)\)",
        patch,
    )
    if match is None:
        return []
    columns: list[SchemaColumn] = []
    for part in _split_defs(match.group("body")):
        column = _sql_column(part, change="add")
        if column is not None:
            columns.append(column)
    return columns


def _column_type(patch: str, column: str) -> str:
    escaped = re.escape(column.strip("\"'"))
    match = re.search(
        rf"(?ix)(?:ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?|ALTER\s+COLUMN\s+){escaped}\s+(?:TYPE\s+)?(?P<type>[\w.()]+)",
        patch,
    )
    return match.group("type") if match else ""


def _split_defs(body: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _sql_column(part: str, *, change: str) -> SchemaColumn | None:
    text = part.strip().rstrip(",")
    if not text or _SKIP_COL.match(text):
        return None
    tokens = text.split()
    if not tokens:
        return None
    name = tokens[0].strip("\"'`")
    if not re.fullmatch(r"[\w]+", name):
        return None
    typ = tokens[1].strip(",") if len(tokens) > 1 else ""
    rest = " ".join(tokens[2:]).upper()
    fk = ""
    fk_column = ""
    ref = re.search(r"REFERENCES\s+([\w.]+)\s*(?:\(\s*([\w]+)\s*\))?", text, re.I)
    if ref:
        fk = ref.group(1)
        fk_column = ref.group(2) or ""
    return SchemaColumn(
        name=name,
        type=typ,
        pk="PRIMARY" in rest,
        fk=fk,
        fk_column=fk_column,
        nullable="NOT NULL" not in rest,
        change=change,
    )


def _add_column_def(patch: str, column: str) -> str:
    escaped = re.escape(column.strip("\"'"))
    match = re.search(
        rf"(?ix)ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?({escaped}\b[^;\n]*)",
        patch,
    )
    return match.group(1) if match else ""


def _relations_from_columns(
    table: str, columns: list[SchemaColumn], *, change: str
) -> list[SchemaRelation]:
    relations: list[SchemaRelation] = []
    for column in columns:
        if not column.fk:
            continue
        relations.append(
            SchemaRelation(
                from_table=table,
                to_table=column.fk,
                from_column=column.name,
                to_column=column.fk_column,
                label=column.fk_column or "fk",
                change=change if change in {"add", "drop", "alter"} else column.change or "add",
            )
        )
    return relations


def _order_tables(
    tables: list[SchemaTable],
    relations: list[SchemaRelation],
    highlight: str,
) -> list[SchemaTable]:
    by_name = {table.name: table for table in tables}
    incoming: dict[str, int] = defaultdict(int)
    edges: dict[str, list[str]] = defaultdict(list)
    for relation in relations:
        if relation.from_table in by_name and relation.to_table in by_name:
            edges[relation.from_table].append(relation.to_table)
            incoming[relation.to_table] += 1
    ordered: list[SchemaTable] = []
    ready = [name for name in by_name if incoming[name] == 0]
    if highlight:
        ready.sort(key=lambda name: (0 if _is_highlight(name, highlight) else 1, name))
    seen: set[str] = set()
    while ready:
        name = ready.pop(0)
        if name in seen:
            continue
        seen.add(name)
        ordered.append(by_name[name])
        for dest in edges[name]:
            incoming[dest] -= 1
            if incoming[dest] == 0:
                ready.append(dest)
    for table in tables:
        if table.name not in seen:
            ordered.append(table)
    return ordered


def _is_highlight(name: str, highlight: str) -> bool:
    if not highlight:
        return False
    return name == highlight or highlight.startswith(f"{name}.") or name.endswith(highlight)


def _render_table(
    table: SchemaTable, *, inner: int, highlight: str
) -> tuple[list[str], list[DiagramSpan]]:
    badge = _TABLE_BADGE.get(table.change, "")
    pointer = "▸ " if _is_highlight(table.name, highlight) else ""
    title = f"{pointer}{table.name}"
    if badge:
        title = f"{title}  [{badge}]"
    rows = table.columns or [
        SchemaColumn(
            name="(no columns listed)", change=table.change if table.change == "drop" else ""
        )
    ]
    width = max(inner, min(48, max(len(title), *(_col_width(column) for column in rows)) + 2))
    edge = "─" * width
    lines = [f"┌{edge}┐", f"│{title.ljust(width)}│", f"├{edge}┤"]
    for column in rows:
        lines.append(f"│{_col_cell(column, width)}│")
    lines.append(f"└{edge}┘")
    spans: list[DiagramSpan] = []
    table_tone = _tone(table.change)
    if table_tone in {"add", "drop"}:
        for row, line in enumerate(lines):
            _add_span(spans, row=row, col=0, width=len(line), tone=table_tone)
    elif table_tone == "alter":
        _add_span(spans, row=1, col=1, width=width, tone=table_tone)
    for index, column in enumerate(rows):
        _add_span(spans, row=3 + index, col=1, width=width, tone=_tone(column.change))
    return lines, spans


def _col_width(column: SchemaColumn) -> int:
    return len(_col_cell(column, 0).rstrip()) + 2


def _col_cell(column: SchemaColumn, width: int) -> str:
    mark = _COL_MARK.get(column.change, " ")
    flags: list[str] = []
    if column.pk:
        flags.append("PK")
    if column.fk:
        flags.append(f"FK {column.fk}" if column.fk not in {"", "FK"} else "FK")
    if column.nullable is False:
        flags.append("NOT NULL")
    left = f"{column.name} {column.type}".strip()
    right = " ".join(flags)
    body = f"{left}  {right}".rstrip() if right else left
    if width <= 0:
        return f" {body} {mark}"
    room = max(1, width - 3)
    if len(body) > room:
        body = body[: max(1, room - 1)] + "…"
    return f" {body.ljust(room)}{mark} "


def _connector_after(
    previous: SchemaTable, current: SchemaTable, relations: list[SchemaRelation]
) -> tuple[list[str], list[DiagramSpan]]:
    matches = [
        relation
        for relation in relations
        if relation.from_table == previous.name and relation.to_table == current.name
    ]
    if not matches:
        return [], []
    pad = " " * 8
    lines = [f"{pad}│"]
    spans: list[DiagramSpan] = []
    tones = {_tone(relation.change) for relation in matches}
    tones.discard("")
    stem = next(iter(tones)) if len(tones) == 1 else ""
    _add_span(spans, row=0, col=len(pad), width=1, tone=stem)
    for relation in matches:
        label = relation.label or _rel_label(relation)
        line = f"{pad}│ {label}" if label else f"{pad}│"
        lines.append(line)
        _add_span(
            spans,
            row=len(lines) - 1,
            col=len(pad),
            width=max(1, len(line) - len(pad)),
            tone=_tone(relation.change) or stem,
        )
    lines.append(f"{pad}▼")
    _add_span(spans, row=len(lines) - 1, col=len(pad), width=1, tone=stem)
    return lines, spans


def _rel_label(relation: SchemaRelation) -> str:
    if relation.from_column and relation.to_column:
        return f"{relation.from_column} → {relation.to_column}"
    return ""


def _side_connector(
    relation: SchemaRelation, *, indent: str = "  "
) -> tuple[list[str], list[DiagramSpan]]:
    left = relation.from_table
    if relation.from_column:
        left = f"{left}.{relation.from_column}"
    right = relation.to_table
    if relation.to_column:
        right = f"{right}.{relation.to_column}"
    label = relation.label or _rel_label(relation) or "fk"
    lines = [f"{indent}┌ {left}", f"{indent}│ {label}", f"{indent}└► {right}"]
    spans: list[DiagramSpan] = []
    tone = _tone(relation.change)
    for row, line in enumerate(lines):
        _add_span(spans, row=row, col=0, width=len(line), tone=tone)
    return lines, spans


def _leftover_relations(
    tables: list[SchemaTable], relations: list[SchemaRelation]
) -> tuple[list[str], list[DiagramSpan]]:
    consecutive: set[tuple[str, str]] = set()
    for index, table in enumerate(tables[1:], start=1):
        consecutive.add((tables[index - 1].name, table.name))
    lines: list[str] = []
    spans: list[DiagramSpan] = []
    for relation in relations:
        if (relation.from_table, relation.to_table) in consecutive:
            continue
        if lines:
            lines.append("")
        chunk, chunk_spans = _side_connector(relation)
        spans.extend(_shift_spans(chunk_spans, len(lines)))
        lines.extend(chunk)
    return lines, spans


def _tone(change: str) -> str:
    token = change.strip().lower()
    return token if token in _COL_MARK else ""


def _add_span(spans: list[DiagramSpan], *, row: int, col: int, width: int, tone: str) -> None:
    if not tone or width <= 0:
        return
    spans.append(DiagramSpan(row=row, col=col, width=width, tone=tone))


def _shift_spans(spans: list[DiagramSpan], rows: int) -> list[DiagramSpan]:
    if not rows:
        return list(spans)
    return [span.model_copy(update={"row": span.row + rows}) for span in spans]


def _hits_from_tables(lines: list[str], tables: list[SchemaTable]) -> list[DiagramHit]:
    hits: list[DiagramHit] = []
    seen: set[str] = set()
    for row, line in enumerate(lines):
        for table in tables:
            if table.name in seen:
                continue
            col = line.find(table.name)
            if col < 0:
                continue
            seen.add(table.name)
            hits.append(
                DiagramHit(row=row, col=col, width=len(table.name), node_id=f"table:{table.name}")
            )
    return hits
