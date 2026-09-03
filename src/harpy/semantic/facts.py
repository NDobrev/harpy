"""Render syntax facts as a greppable sidecar. Written once per semantic run."""

from __future__ import annotations

from pathlib import Path

from harpy.models import AnalysisResult, FileFacts

FACTS_FILENAME = "SYMBOL_FACTS.md"
MAX_FACTS_CHARS = 80_000


def render_symbol_facts(facts: list[FileFacts]) -> str:
    lines = [
        "# SYMBOL FACTS (tree-sitter; syntax only, no type resolution)",
        "# grep by path to pull facts for one file.",
        "",
    ]
    for item in facts:
        lines.append(f"## {item.path}")
        for symbol in item.symbols:
            sig = f' sig="{symbol.signature}"' if symbol.signature else ""
            vis = f" {symbol.visibility}" if symbol.visibility else ""
            kind = symbol.kind or "symbol"
            lines.append(
                f"DEF  {item.path}:{symbol.start_line}-{symbol.end_line} "
                f"{kind} {symbol.name}{vis}{sig}"
            )
        for imported in item.imports:
            names = f" names=[{','.join(imported.names)}]" if imported.names else ""
            lines.append(f"IMP  {item.path}:{imported.line} module={imported.module}{names}")
        for route in item.routes:
            handler = f" handler={route.handler}" if route.handler else ""
            lines.append(f"ROUTE {item.path}:{route.line} {route.method} {route.route}{handler}")
        for ddl in item.ddl:
            pieces = [f"table={ddl.table}"]
            if ddl.column:
                pieces.append(f"column={ddl.column}")
            if ddl.col_type:
                pieces.append(f"type={ddl.col_type}")
            if ddl.nullable is not None:
                pieces.append(f"nullable={str(ddl.nullable).lower()}")
            if ddl.fk_table:
                pieces.append(f"fk={ddl.fk_table}.{ddl.fk_column}".rstrip("."))
            lines.append(f"DDL  {item.path}:{ddl.line} {ddl.operation} {' '.join(pieces)}")
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    if len(text) > MAX_FACTS_CHARS:
        return text[:MAX_FACTS_CHARS] + "\n# … truncated\n"
    return text


def write_symbol_facts(result: AnalysisResult, workspace: Path) -> Path | None:
    if not result.file_facts:
        return None
    path = workspace / FACTS_FILENAME
    path.write_text(render_symbol_facts(result.file_facts), encoding="utf-8")
    return path
