from __future__ import annotations

from harpy.models import DiffHunk, LogicalChange
from harpy.tui.change_tree import (
    build_change_forest,
    files_for_change,
    flatten_forest,
    overlap,
    visible_rows,
)


def _change(
    change_id: str,
    title: str,
    *,
    files: list[str] | None = None,
    domains: list[str] | None = None,
    symbols: list[str] | None = None,
    hunk_ids: list[str] | None = None,
    priority: float = 10,
    risk: str = "LOW",
) -> LogicalChange:
    return LogicalChange(
        id=change_id,
        title=title,
        files=files or [],
        domains=domains or [],
        affected_symbols=symbols or [],
        hunk_ids=hunk_ids or [],
        review_priority=priority,
        risk=risk,
    )


def test_shared_files_nest_under_higher_priority_parent() -> None:
    parent = _change(
        "C1",
        "fail closed",
        files=["src/services/fees.ts"],
        domains=["BUSINESS_LOGIC"],
        priority=80,
        risk="HIGH",
    )
    child = _change(
        "C2",
        "quote reports missing destinations",
        files=["src/services/fees.ts", "src/routes/fees.ts"],
        domains=["API"],
        priority=40,
    )
    forest = build_change_forest([child, parent])
    assert len(forest) == 1
    assert forest[0].name == "Business Logic"
    assert forest[0].roots[0].change.id == "C1"
    assert [node.change.id for node in forest[0].roots[0].children] == ["C2"]


def test_unrelated_changes_stay_siblings() -> None:
    left = _change("C1", "fees", files=["src/fees.ts"], domains=["fees"], priority=50)
    right = _change("C2", "webhooks", files=["src/webhooks.ts"], domains=["webhooks"], priority=40)
    forest = build_change_forest([left, right])
    names = {group.name for group in forest}
    assert names == {"Fees", "Webhooks"}
    assert all(len(group.roots) == 1 and not group.roots[0].children for group in forest)


def test_test_change_nests_under_implementation() -> None:
    impl = _change(
        "C1",
        "per-leg settlement",
        files=["src/services/payouts/broadcast.ts"],
        domains=["BUSINESS_LOGIC"],
        symbols=["runBroadcast"],
        priority=70,
    )
    test = _change(
        "C2",
        "broadcast tests",
        files=["tests/services/payouts-evm.test.ts"],
        domains=["TEST"],
        symbols=["runBroadcast"],
        priority=5,
    )
    forest = build_change_forest([impl, test])
    assert forest[0].roots[0].change.id == "C1"
    assert forest[0].roots[0].children[0].change.id == "C2"
    assert overlap(impl, test) >= 2


def test_flatten_puts_each_changes_files_as_leaves() -> None:
    parent = _change(
        "C1",
        "fail closed when a beneficiary has no omnibus",
        files=["src/services/fees.ts"],
        domains=["BUSINESS_LOGIC"],
        priority=80,
    )
    child = _change(
        "C2",
        "quote reports missing destinations",
        files=["src/services/fees.ts", "src/routes/fees.ts"],
        domains=["API"],
        priority=40,
    )
    rows = flatten_forest(build_change_forest([parent, child]), [])
    assert rows[0].kind == "group"
    assert [(row.kind, row.change_id, row.file_path) for row in rows[1:]] == [
        ("change", "C1", None),
        ("file", "C1", "src/services/fees.ts"),
        ("change", "C2", None),
        ("file", "C2", "src/services/fees.ts"),
        ("file", "C2", "src/routes/fees.ts"),
    ]
    assert "\n" in rows[1].render()
    assert rows[-1].kind == "file"


def test_files_for_change_uses_only_that_changes_hunks() -> None:
    change = _change("C1", "fees", files=["src/fees.ts"], hunk_ids=["H1"])
    hunks = [
        DiffHunk(
            id="H1",
            file_path="src/fees.ts",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            patch="+a\n",
        ),
        DiffHunk(
            id="H2",
            file_path="src/other.ts",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            patch="+b\n",
        ),
    ]
    assert files_for_change(change, hunks) == ["src/fees.ts"]


def test_visible_rows_hides_children_of_a_collapsed_change() -> None:
    parent = _change(
        "C1",
        "fail closed",
        files=["src/services/fees.ts"],
        domains=["BUSINESS_LOGIC"],
        priority=80,
    )
    child = _change(
        "C2",
        "quote reports",
        files=["src/services/fees.ts"],
        domains=["API"],
        priority=40,
    )
    rows = flatten_forest(build_change_forest([parent, child]), [])
    hidden = visible_rows(rows, {"change:C1"})
    assert [row.kind for row in hidden] == ["group", "change"]
    assert hidden[1].change_id == "C1"
    assert hidden[1].render(collapsed=True).startswith("  ▶ ")
