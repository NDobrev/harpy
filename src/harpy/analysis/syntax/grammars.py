"""Lazy language and query loading. Missing grammars degrade to empty facts."""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from tree_sitter import Language, Query

QUERIES_DIR = Path(__file__).resolve().parent / "queries"

_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".sql": "sql",
}

_QUERY_FILE: dict[str, str] = {
    "python": "python.scm",
    "typescript": "typescript.scm",
    "tsx": "tsx.scm",
    "go": "go.scm",
    "rust": "rust.scm",
    "sql": "sql.scm",
}

_LANGUAGE_ATTR: dict[str, tuple[str, str]] = {
    "python": ("tree_sitter_python", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "go": ("tree_sitter_go", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "sql": ("tree_sitter_sql", "language"),
}


def language_for_path(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    return _EXTENSIONS.get(suffix)


@lru_cache(maxsize=16)
def load_language(name: str) -> Any | None:
    spec = _LANGUAGE_ATTR.get(name)
    if spec is None:
        return None
    module_name, attr = spec
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attr)
        return Language(factory())
    except (OSError, TypeError, ValueError, RuntimeError, AttributeError, ModuleNotFoundError):
        return None


@lru_cache(maxsize=16)
def load_query(name: str) -> Any | None:
    language = load_language(name)
    if language is None:
        return None
    filename = _QUERY_FILE.get(name)
    if filename is None:
        return None
    path = QUERIES_DIR / filename
    if not path.is_file():
        return None
    try:
        return Query(language, path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, RuntimeError):
        return None
