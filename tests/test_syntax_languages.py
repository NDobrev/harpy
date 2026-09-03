from __future__ import annotations

from pathlib import Path

from harpy.analysis.syntax.extract import extract_file_facts, symbols_from_facts
from harpy.models import DiffHunk

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "syntax"


def test_typescript_qualified_symbols_and_imports() -> None:
    source = (FIXTURES / "users.ts").read_text(encoding="utf-8")
    facts = extract_file_facts(source, path="src/api/users.ts")
    names = {symbol.name for symbol in facts.symbols}
    assert "deleteUser" in names
    assert "UserService" in names
    assert "UserService.purge" in names
    assert "hidden" in names
    exported = {symbol.name for symbol in facts.symbols if symbol.visibility == "public"}
    assert "deleteUser" in exported
    assert "UserService" in exported
    assert facts.imports
    assert any("./db" in item.module or "db" in item.module for item in facts.imports)
    hunk = DiffHunk(
        id="H1",
        file_path="src/api/users.ts",
        old_start=3,
        old_count=3,
        new_start=3,
        new_count=3,
        patch="",
    )
    assert "deleteUser" in symbols_from_facts(facts, hunk)


def test_go_exported_and_receiver_methods() -> None:
    source = (FIXTURES / "users.go").read_text(encoding="utf-8")
    facts = extract_file_facts(source, path="src/api/users.go")
    names = {symbol.name for symbol in facts.symbols}
    assert "DeleteUser" in names
    assert "UserService" in names
    assert "UserService.Purge" in names
    assert "hidden" in names
    visibility = {symbol.name: symbol.visibility for symbol in facts.symbols}
    assert visibility["DeleteUser"] == "public"
    assert visibility["hidden"] == "private"
    assert any(route.route == "/users" for route in facts.routes)


def test_rust_pub_and_impl_methods() -> None:
    source = (FIXTURES / "users.rs").read_text(encoding="utf-8")
    facts = extract_file_facts(source, path="src/api/users.rs")
    names = {symbol.name for symbol in facts.symbols}
    assert "delete_user" in names
    assert "UserService" in names
    assert "UserService.purge" in names
    assert "hidden" in names
    visibility = {symbol.name: symbol.visibility for symbol in facts.symbols}
    assert visibility["delete_user"] == "public"
    assert visibility["hidden"] == "private"
    assert any(route.method == "GET" and route.route == "/users" for route in facts.routes)
