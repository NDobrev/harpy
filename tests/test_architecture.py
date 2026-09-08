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


V2_LAYERS = ("storage", "evidence", "review", "verification", "export")
FIXTURE_SRC = Path(__file__).resolve().parent / "fixtures" / "architecture" / "harpy"


def _full_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _matches(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def boundary_violations(harpy_root: Path) -> list[str]:
    violations: list[str] = []
    tui = harpy_root / "tui"
    if tui.is_dir():
        banned = (
            "harpy.storage",
            "harpy.evidence",
            "harpy.semantic",
            "harpy.github",
            "harpy.verification",
            "harpy.git",
        )
        for path in tui.rglob("*.py"):
            for name in _full_imports(path):
                if any(_matches(name, prefix) for prefix in banned):
                    violations.append(f"{path}: TUI imports {name}")
    review = harpy_root / "review"
    if review.is_dir():
        for path in review.rglob("*.py"):
            for name in _full_imports(path):
                if name == "subprocess" or _matches(name, "harpy.semantic"):
                    violations.append(f"{path}: review imports {name}")
    evidence = harpy_root / "evidence"
    if evidence.is_dir():
        for path in evidence.rglob("*.py"):
            for name in _full_imports(path):
                if _matches(name, "harpy.semantic"):
                    violations.append(f"{path}: evidence imports {name}")
    semantic = harpy_root / "semantic"
    if semantic.is_dir():
        for path in semantic.rglob("*.py"):
            for name in _full_imports(path):
                if _matches(name, "harpy.verification") or _matches(name, "harpy.tui"):
                    violations.append(f"{path}: semantic imports {name}")
    scoring = harpy_root / "analysis" / "scoring.py"
    if scoring.is_file():
        for name in _imports(scoring):
            if name not in {"__future__", "harpy.models"}:
                violations.append(f"{scoring}: scoring imports {name}")
    return violations


def test_v2_layer_packages_exist() -> None:
    for name in V2_LAYERS:
        assert (SRC / name / "__init__.py").is_file(), name


def test_v2_src_respects_new_boundaries() -> None:
    assert boundary_violations(SRC) == []


def test_tui_does_not_import_storage_or_verification() -> None:
    banned = ("harpy.storage", "harpy.evidence", "harpy.github", "harpy.verification", "harpy.git")
    for path in (SRC / "tui").rglob("*.py"):
        for name in _full_imports(path):
            assert not any(_matches(name, prefix) for prefix in banned), path


def test_review_does_not_import_semantic_or_subprocess() -> None:
    review = SRC / "review"
    assert review.is_dir()
    for path in review.rglob("*.py"):
        for name in _full_imports(path):
            assert name != "subprocess", path
            assert not _matches(name, "harpy.semantic"), path


def test_evidence_does_not_import_semantic() -> None:
    evidence = SRC / "evidence"
    assert evidence.is_dir()
    for path in evidence.rglob("*.py"):
        for name in _full_imports(path):
            assert not _matches(name, "harpy.semantic"), path


def test_semantic_does_not_import_verification() -> None:
    for path in (SRC / "semantic").rglob("*.py"):
        for name in _full_imports(path):
            assert not _matches(name, "harpy.verification"), path


def test_architecture_fixtures_are_detected() -> None:
    violations = boundary_violations(FIXTURE_SRC)
    joined = "\n".join(violations)
    assert "harpy.storage" in joined
    assert "harpy.semantic" in joined
    assert "harpy.verification" in joined
    assert "scoring imports" in joined
    assert violations, "deliberate fixture violations must fail the checker"
