from __future__ import annotations

from harpy.analysis.symbols import build_symbol_map, symbols_for_hunk
from harpy.analysis.syntax.extract import extract_file_facts, symbols_from_facts
from harpy.models import DiffHunk

SOURCE = """
class PermissionService:
    def has_admin_access(self, user):
        return True

    def can_delete_user(self, user):
        return user.is_admin

def helper():
    return 1
"""


def test_tree_sitter_python_matches_ast_names() -> None:
    ast_names = [span.name for span in build_symbol_map(SOURCE)]
    facts = extract_file_facts(SOURCE, path="src/auth/permissions.py")
    names = [symbol.name for symbol in facts.symbols]
    for name in ast_names:
        assert name in names
    assert facts.language == "python"
    assert any(symbol.visibility == "public" for symbol in facts.symbols)


def test_tree_sitter_hunk_maps_to_same_method() -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="p.py",
        old_start=6,
        old_count=2,
        new_start=6,
        new_count=2,
        patch="",
    )
    facts = extract_file_facts(SOURCE, path="p.py")
    assert "PermissionService.can_delete_user" in symbols_from_facts(facts, hunk)
    assert "PermissionService.can_delete_user" in symbols_for_hunk(hunk, SOURCE)


def test_python_import_and_route_facts() -> None:
    source = (
        "from .db import get_pool\n"
        "import os\n"
        "\n"
        '@app.get("/users")\n'
        "def list_users():\n"
        "    return []\n"
    )
    facts = extract_file_facts(source, path="src/api/users.py")
    modules = {item.module for item in facts.imports}
    assert ".db" in modules or any("db" in item.module for item in facts.imports)
    assert any(item.names == ["get_pool"] for item in facts.imports)
    assert any(route.method == "GET" and route.route == "/users" for route in facts.routes)
    assert any(route.handler == "list_users" for route in facts.routes)
