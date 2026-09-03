"""Python AST symbol map."""

from __future__ import annotations

import ast
from pathlib import Path

from harpy.models import DiffHunk


class SymbolSpan:
    def __init__(self, name: str, start: int, end: int) -> None:
        self.name = name
        self.start = start
        self.end = end


def _end_lineno(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None)
    if isinstance(end, int):
        return end
    return int(getattr(node, "lineno", 1))


def build_symbol_map(source: str, *, module: str = "") -> list[SymbolSpan]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    spans: list[SymbolSpan] = []
    prefix = f"{module}." if module else ""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            start = int(node.lineno)
            end = _end_lineno(node)
            class_name = f"{prefix}{node.name}"
            spans.append(SymbolSpan(class_name, start, end))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    spans.append(
                        SymbolSpan(
                            f"{class_name}.{child.name}", int(child.lineno), _end_lineno(child)
                        )
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(
            getattr(node, "parent", None), ast.Module
        ):
            spans.append(SymbolSpan(f"{prefix}{node.name}", int(node.lineno), _end_lineno(node)))
    # Module-level functions: walk body only
    try:
        parsed = ast.parse(source)
    except SyntaxError:
        return spans
    for node in parsed.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = f"{prefix}{node.name}"
            if not any(span.name == name for span in spans):
                spans.append(SymbolSpan(name, int(node.lineno), _end_lineno(node)))
    return sorted(spans, key=lambda item: (item.start, -item.end))


def symbols_for_hunk(hunk: DiffHunk, source: str, *, module: str = "") -> list[str]:
    spans = build_symbol_map(source, module=module)
    start = hunk.new_start
    end = hunk.new_start + max(hunk.new_count, 1) - 1
    names: list[str] = []
    for span in spans:
        if span.end < start or span.start > end:
            continue
        names.append(span.name)
    return names


def read_source(worktree: Path, relative: str) -> str:
    path = worktree / relative
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
