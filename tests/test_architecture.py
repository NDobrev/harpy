from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "harpy"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_subprocess_only_in_proc() -> None:
    for path in SRC.rglob("*.py"):
        imported = _imports(path)
        if path.name == "proc.py":
            assert "subprocess" in imported
            continue
        assert "subprocess" not in imported, path


def test_tui_does_not_import_semantic() -> None:
    for path in (SRC / "tui").rglob("*.py"):
        for name in _imports(path):
            assert not name.startswith("harpy.semantic"), path


def test_semantic_does_not_import_tui() -> None:
    for path in (SRC / "semantic").rglob("*.py"):
        for name in _imports(path):
            assert not name.startswith("harpy.tui"), path


def test_syntax_does_not_import_tui_or_semantic() -> None:
    syntax = SRC / "analysis" / "syntax"
    assert syntax.is_dir()
    for path in syntax.rglob("*.py"):
        for name in _imports(path):
            assert not name.startswith("harpy.tui"), path
            assert not name.startswith("harpy.semantic"), path


def test_scoring_imports_only_models() -> None:
    path = SRC / "analysis" / "scoring.py"
    for name in _imports(path):
        if name in {"__future__", "harpy.models"}:
            continue
        raise AssertionError(f"scoring.py imports {name}")
