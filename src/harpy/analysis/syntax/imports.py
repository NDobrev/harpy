"""Drop grep hits that cannot import the defining module."""

from __future__ import annotations

from pathlib import Path

from harpy.models import FileFacts, ReferenceHit

_SKIP_ROOTS = {"src", "lib", "app", "pkg", "internal", "source"}


def filter_hits(hits: list[ReferenceHit], facts: list[FileFacts]) -> list[ReferenceHit]:
    if not hits or not facts:
        return hits
    defining = _defining_paths(facts)
    facts_by_path = {item.path.replace("\\", "/"): item for item in facts}
    kept: list[ReferenceHit] = []
    for hit in hits:
        path = hit.path.replace("\\", "/")
        owners = defining.get(hit.symbol, [])
        if not owners:
            kept.append(hit)
            continue
        if path in owners:
            kept.append(hit)
            continue
        if hit.kind == "test":
            kept.append(hit)
            continue
        file_facts = facts_by_path.get(path)
        if file_facts is None:
            kept.append(hit)
            continue
        if _imports_any(file_facts, owners):
            kept.append(hit)
    return kept


def _defining_paths(facts: list[FileFacts]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for item in facts:
        path = item.path.replace("\\", "/")
        for symbol in item.symbols:
            mapping.setdefault(symbol.name, [])
            if path not in mapping[symbol.name]:
                mapping[symbol.name].append(path)
    return mapping


def _imports_any(facts: FileFacts, owners: list[str]) -> bool:
    keys: set[str] = set()
    for owner in owners:
        keys.update(_path_keys(owner))
    for imported in facts.imports:
        if _module_keys(imported.module) & keys:
            return True
    return False


def _path_keys(path: str) -> set[str]:
    rel = path.replace("\\", "/")
    stem = str(Path(rel).with_suffix(""))
    parts = [part for part in stem.split("/") if part]
    keys = {rel, stem, "/".join(parts), ".".join(parts)}
    if parts:
        keys.add(parts[-1])
    trimmed = list(parts)
    while trimmed and trimmed[0] in _SKIP_ROOTS:
        trimmed = trimmed[1:]
        keys.add("/".join(trimmed))
        keys.add(".".join(trimmed))
        if trimmed:
            keys.add(trimmed[-1])
    return {key for key in keys if key}


def _module_keys(module: str) -> set[str]:
    raw = module.strip().strip("'\"")
    raw = raw.replace("\\", "/")
    raw = raw[2:] if raw.startswith("./") else raw
    raw = raw[3:] if raw.startswith("../") else raw
    dotted = raw.replace("/", ".").replace("::", ".")
    slashed = dotted.replace(".", "/")
    keys = {raw, dotted, slashed}
    if dotted:
        keys.add(dotted.split(".")[-1])
    return {key for key in keys if key}
