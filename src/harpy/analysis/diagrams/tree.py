"""Approximate blast-radius trees from references. Not a perfect call graph."""

from __future__ import annotations

from harpy.models import (
    AnalysisResult,
    ApiEndpointImpact,
    BlastTree,
    BlastTreeNode,
    DbChangeImpact,
    DiagramHit,
    LogicalChange,
    ReferenceHit,
    RenderedDiagram,
)

_KIND_ORDER = ("route", "caller", "worker", "import", "test", "configuration", "file", "unknown")
_DEFAULT_CAP = 12


def build_blast_tree(
    *,
    root_label: str,
    references: list[ReferenceHit],
    callers: list[str] | None = None,
    files: list[str] | None = None,
    symbols: list[str] | None = None,
    needles: list[str] | None = None,
    cap: int = _DEFAULT_CAP,
) -> BlastTree | None:
    root = BlastTreeNode(label=root_label or "impact", kind="root")
    children = _children_from_refs(
        references,
        files=files or [],
        symbols=symbols or [],
        needles=needles or [],
        cap=cap,
    )
    seen_paths = {child.path for child in children if child.path}
    seen_labels = {child.label for child in children}
    for caller in callers or []:
        if not caller or caller in seen_labels:
            continue
        children.append(BlastTreeNode(label=caller, kind="caller"))
        seen_labels.add(caller)
        if len(children) >= cap:
            break
    for path in files or []:
        if not path or path in seen_paths:
            continue
        children.append(BlastTreeNode(label=path, kind="file", path=path))
        seen_paths.add(path)
        if len(children) >= cap:
            break
    if not children:
        return None
    children.sort(key=lambda node: _KIND_ORDER.index(node.kind) if node.kind in _KIND_ORDER else 99)
    root.children = children[:cap]
    return BlastTree(root=root)


def attach_blast_trees(result: AnalysisResult) -> None:
    for api_impact in result.api_impacts:
        _fill_tree(result, api_impact)
    for db_impact in result.db_impacts:
        _fill_tree(result, db_impact)


def render_blast_tree(tree: BlastTree) -> RenderedDiagram:
    lines = ["BLAST RADIUS", ""]
    hits: list[DiagramHit] = []
    _walk(tree.root, lines, hits, prefix="", last=True, is_root=True)
    return RenderedDiagram(title="BLAST RADIUS", kind="tree", lines=lines, hits=hits)


def _fill_tree(result: AnalysisResult, impact: ApiEndpointImpact | DbChangeImpact) -> None:
    if impact.tree is not None and impact.tree.root.children:
        return
    for diagram in impact.diagrams:
        if diagram.tree is not None and diagram.tree.root.children:
            if impact.tree is None:
                impact.tree = diagram.tree
            return
    change = _linked_change(result, impact.change_id)
    if isinstance(impact, ApiEndpointImpact):
        root = f"{impact.method} {impact.path}".strip() or impact.summary or "endpoint"
        callers = list(impact.callers)
        needles = [impact.method, impact.path, impact.summary]
    else:
        root = impact.target or impact.summary or "schema"
        callers = list(impact.objects)
        needles = [impact.target, impact.operation, *impact.objects]
    symbols = list(change.affected_symbols) if change is not None else []
    tree = build_blast_tree(
        root_label=root,
        references=result.references,
        callers=callers,
        files=list(impact.files),
        symbols=symbols,
        needles=[item for item in needles if item],
    )
    if tree is not None:
        impact.tree = tree


def _linked_change(result: AnalysisResult, change_id: str) -> LogicalChange | None:
    if not change_id:
        return None
    for change in result.changes:
        if change.id == change_id:
            return change
    return None


def _children_from_refs(
    references: list[ReferenceHit],
    *,
    files: list[str],
    symbols: list[str],
    needles: list[str],
    cap: int,
) -> list[BlastTreeNode]:
    children: list[BlastTreeNode] = []
    seen: set[tuple[str, str, int]] = set()
    file_set = set(files)
    symbol_set = set(symbols)
    for hit in references:
        if not _relevant(hit, symbols=symbol_set, files=file_set, needles=needles):
            continue
        key = (hit.path, hit.symbol, hit.line)
        if key in seen:
            continue
        seen.add(key)
        label = hit.symbol or hit.path
        extra = f"{hit.path}:{hit.line}" if hit.path else ""
        if extra and extra not in label:
            label = f"{label}  {extra}".strip()
        children.append(
            BlastTreeNode(
                label=label,
                kind=hit.kind or "unknown",
                evidence=str(hit.evidence),
                path=hit.path,
                line=hit.line,
            )
        )
        if len(children) >= cap:
            break
    return children


def _relevant(
    hit: ReferenceHit,
    *,
    symbols: set[str],
    files: set[str],
    needles: list[str],
) -> bool:
    if symbols and hit.symbol in symbols:
        return True
    if hit.path and hit.path in files:
        return True
    short = hit.symbol.split(".")[-1]
    haystack = f"{hit.symbol} {hit.path} {hit.snippet}"
    for needle in needles:
        if needle and needle in haystack:
            return True
        if short and needle and short in needle:
            return True
    return False


def _walk(
    node: BlastTreeNode,
    lines: list[str],
    hits: list[DiagramHit],
    *,
    prefix: str,
    last: bool,
    is_root: bool,
) -> None:
    if is_root:
        text = node.label
        lines.append(text)
        hits.append(DiagramHit(row=len(lines) - 1, col=0, width=len(text), node_id="tree:root"))
        child_prefix = ""
    else:
        branch = "└── " if last else "├── "
        kind = f"{node.kind}  " if node.kind else ""
        text = f"{kind}{node.label}"
        line = f"{prefix}{branch}{text}"
        lines.append(line)
        col = len(prefix) + len(branch)
        hits.append(
            DiagramHit(
                row=len(lines) - 1,
                col=col,
                width=len(text),
                node_id=f"tree:{node.path or node.label}",
                path=node.path,
                line=node.line,
            )
        )
        child_prefix = f"{prefix}{'    ' if last else '│   '}"
    last_index = len(node.children) - 1
    for index, child in enumerate(node.children):
        _walk(child, lines, hits, prefix=child_prefix, last=index == last_index, is_root=False)
