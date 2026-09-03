from __future__ import annotations

from pathlib import Path

from harpy.analysis.references import GitLsFilesSearcher, classify_hit
from harpy.analysis.syntax.imports import filter_hits
from harpy.models import FileFacts, ImportFact, ReferenceHit, SymbolFact


def test_classify_kinds() -> None:
    kind, _ = classify_hit("tests/test_user.py", "can_delete_user()", "can_delete_user")
    assert kind == "test"
    kind, _ = classify_hit("src/api.py", "from x import can_delete_user", "can_delete_user")
    assert kind == "import"


def test_python_fallback(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "users.py").write_text(
        "def caller():\n    can_delete_user()\n", encoding="utf-8"
    )
    (tmp_path / ".git").mkdir()
    hits = GitLsFilesSearcher().search("can_delete_user", root=tmp_path, cap=5)
    assert hits
    assert hits[0].kind == "caller"


def test_import_graph_drops_unrelated_homonyms() -> None:
    facts = [
        FileFacts(
            path="src/auth/permissions.py",
            language="python",
            symbols=[SymbolFact(name="can_delete_user", kind="function", start_line=1, end_line=2)],
        ),
        FileFacts(
            path="src/api/users.py",
            language="python",
            imports=[ImportFact(module="auth.permissions", names=["can_delete_user"])],
        ),
        FileFacts(
            path="src/unrelated.py",
            language="python",
            imports=[ImportFact(module="os", names=[])],
        ),
    ]
    hits = [
        ReferenceHit(
            symbol="can_delete_user", path="src/auth/permissions.py", line=1, kind="caller"
        ),
        ReferenceHit(symbol="can_delete_user", path="src/api/users.py", line=4, kind="caller"),
        ReferenceHit(symbol="can_delete_user", path="src/unrelated.py", line=9, kind="caller"),
        ReferenceHit(symbol="can_delete_user", path="tests/test_user.py", line=3, kind="test"),
    ]
    kept = {(hit.path, hit.kind) for hit in filter_hits(hits, facts)}
    assert ("src/auth/permissions.py", "caller") in kept
    assert ("src/api/users.py", "caller") in kept
    assert ("tests/test_user.py", "test") in kept
    assert ("src/unrelated.py", "caller") not in kept
