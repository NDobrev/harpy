"""Group logical changes by domain, then nest by shared files/symbols."""

from __future__ import annotations

from dataclasses import dataclass, field

from harpy.models import DiffHunk, LogicalChange

_TEST_HINTS = ("/test/", "/tests/", "_test.", ".test.", "test_")


@dataclass
class ChangeNode:
    change: LogicalChange
    children: list[ChangeNode] = field(default_factory=list)


@dataclass
class ChangeGroup:
    name: str
    roots: list[ChangeNode]


def group_key(change: LogicalChange) -> str:
    for domain in change.domains:
        token = domain.strip()
        if not token or token.upper() in {"UNKNOWN", "TEST"}:
            continue
        return token.replace("_", " ").title()
    if change.affected_components:
        return change.affected_components[0]
    if change.files:
        parts = change.files[0].replace("\\", "/").split("/")
        if parts[0] in {"src", "lib", "app", "tests"} and len(parts) > 1:
            return parts[1]
        return parts[0]
    return "Other"


def is_test_change(change: LogicalChange) -> bool:
    if any(domain.upper() == "TEST" for domain in change.domains):
        return True
    return any(
        hint in path.replace("\\", "/").lower() for path in change.files for hint in _TEST_HINTS
    )


def overlap(left: LogicalChange, right: LogicalChange) -> int:
    score = 0
    score += 3 * len(set(left.files) & set(right.files))
    score += 2 * len(set(left.affected_symbols) & set(right.affected_symbols))
    score += 2 * len(set(left.affected_components) & set(right.affected_components))
    if is_test_change(left) != is_test_change(right):
        score += _path_prefix_bonus(left.files, right.files)
    return score


def _path_prefix_bonus(left: list[str], right: list[str]) -> int:
    best = 0
    for source in left:
        for other in right:
            shared = _shared_prefix(source.replace("\\", "/"), other.replace("\\", "/"))
            best = max(best, shared)
    return 1 if best >= 2 else 0


def _shared_prefix(left: str, right: str) -> int:
    a = left.split("/")
    b = right.split("/")
    count = 0
    for one, two in zip(a, b, strict=False):
        if one != two:
            break
        count += 1
    return count


def build_change_forest(changes: list[LogicalChange]) -> list[ChangeGroup]:
    ordered = sorted(changes, key=lambda item: (-item.review_priority, item.id))
    parent_of: dict[str, str | None] = {}
    placed: list[LogicalChange] = []
    for change in ordered:
        best: LogicalChange | None = None
        best_score = 1
        for prior in placed:
            score = overlap(change, prior)
            if score > best_score:
                best_score = score
                best = prior
        parent_of[change.id] = best.id if best else None
        placed.append(change)

    by_id = {change.id: ChangeNode(change) for change in ordered}
    roots: list[ChangeNode] = []
    for change in ordered:
        parent_id = parent_of[change.id]
        if parent_id is None:
            roots.append(by_id[change.id])
            continue
        by_id[parent_id].children.append(by_id[change.id])

    grouped: dict[str, list[ChangeNode]] = {}
    for root in roots:
        grouped.setdefault(group_key(root.change), []).append(root)

    def group_priority(name: str) -> float:
        nodes = grouped[name]
        return max(_subtree_priority(node) for node in nodes)

    return [
        ChangeGroup(name=name, roots=grouped[name])
        for name in sorted(grouped, key=lambda item: (-group_priority(item), item))
    ]


def _subtree_priority(node: ChangeNode) -> float:
    return max(
        [node.change.review_priority, *(_subtree_priority(child) for child in node.children)],
        default=0,
    )


def visible_rows(rows: list[DisplayRow], collapsed: set[str]) -> list[DisplayRow]:
    skip_deeper_than: int | None = None
    visible: list[DisplayRow] = []
    for row in rows:
        if skip_deeper_than is not None:
            if row.depth > skip_deeper_than:
                continue
            skip_deeper_than = None
        visible.append(row)
        if row.node_key and row.has_children and row.node_key in collapsed:
            skip_deeper_than = row.depth
    return visible


def first_change_id(groups: list[ChangeGroup]) -> str | None:
    for group in groups:
        for root in group.roots:
            return root.change.id
    return None


def files_for_change(change: LogicalChange, hunks: list[DiffHunk]) -> list[str]:
    paths = list(dict.fromkeys(change.files))
    wanted = set(change.hunks or change.hunk_ids)
    for hunk in hunks:
        if wanted and hunk.id not in wanted:
            continue
        if not wanted and change.files and hunk.file_path not in change.files:
            continue
        if hunk.file_path not in paths:
            paths.append(hunk.file_path)
    return paths


def file_label(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if len(parts) > 2:
        return "/".join(parts[-2:])
    return path


@dataclass
class DisplayRow:
    kind: str
    depth: int
    label: str
    change_id: str | None
    file_path: str | None
    selectable: bool
    last: bool = False
    node_key: str | None = None
    parent_key: str | None = None
    has_children: bool = False

    def render(self, *, collapsed: bool = False) -> str:
        marker = ""
        if self.has_children:
            marker = "▶ " if collapsed else "▼ "
        if self.kind == "group":
            return f"{marker}{self.label}"
        pad = "  " * self.depth
        if self.kind == "change":
            head, _, title = self.label.partition("\n")
            first = f"{pad}{marker}{head}"
            if not title:
                return first
            return f"{first}\n{pad}{title}"
        branch = "└─ " if self.last else "├─ "
        return f"{pad}{branch}{self.label}"


def flatten_forest(
    groups: list[ChangeGroup],
    hunks: list[DiffHunk],
) -> list[DisplayRow]:
    rows: list[DisplayRow] = []
    for group in groups:
        group_key_value = f"group:{group.name}"
        rows.append(
            DisplayRow(
                kind="group",
                depth=0,
                label=group.name,
                change_id=None,
                file_path=None,
                selectable=True,
                node_key=group_key_value,
                has_children=bool(group.roots),
            )
        )
        for root in group.roots:
            _walk(root, depth=1, hunks=hunks, rows=rows, parent_key=group_key_value)
    return rows


def _walk(
    node: ChangeNode,
    *,
    depth: int,
    hunks: list[DiffHunk],
    rows: list[DisplayRow],
    parent_key: str | None,
) -> None:
    key = f"change:{node.change.id}"
    files = files_for_change(node.change, hunks)
    rows.append(
        DisplayRow(
            kind="change",
            depth=depth,
            label=_heading(node.change),
            change_id=node.change.id,
            file_path=None,
            selectable=True,
            node_key=key,
            parent_key=parent_key,
            has_children=bool(files or node.children),
        )
    )
    for index, path in enumerate(files):
        last = index == len(files) - 1 and not node.children
        rows.append(
            DisplayRow(
                kind="file",
                depth=depth + 1,
                label=file_label(path),
                change_id=node.change.id,
                file_path=path,
                selectable=True,
                last=last,
                parent_key=key,
            )
        )
    for child in node.children:
        _walk(child, depth=depth + 1, hunks=hunks, rows=rows, parent_key=key)


_MARK = {"CRITICAL": "🔴", "HIGH": "🔴", "MEDIUM": "🟠", "LOW": "⚪"}


def _heading(change: LogicalChange) -> str:
    extra = ""
    if change.unexpectedness > 70:
        extra += " !"
    if change.confidence < 0.6:
        extra += " ?"
    mark = _MARK.get(change.risk, "🟡")
    return f"{change.review_priority:3.0f} {mark} {change.risk}{extra}\n{change.title}"
