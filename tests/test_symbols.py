from __future__ import annotations

from harpy.analysis.symbols import build_symbol_map, symbols_for_hunk
from harpy.models import DiffHunk

SOURCE = """
class PermissionService:
    def has_admin_access(self, user):
        return True

    def can_delete_user(self, user):
        return user.is_admin
"""


def test_symbol_map() -> None:
    spans = build_symbol_map(SOURCE)
    names = [span.name for span in spans]
    assert "PermissionService" in names
    assert "PermissionService.can_delete_user" in names


def test_hunk_maps_to_method() -> None:
    hunk = DiffHunk(
        id="H1",
        file_path="p.py",
        old_start=6,
        old_count=2,
        new_start=6,
        new_count=2,
        patch="",
    )
    names = symbols_for_hunk(hunk, SOURCE)
    assert "PermissionService.can_delete_user" in names
