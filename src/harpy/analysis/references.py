"""Reference search: ripgrep with a Python fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from harpy.models import EvidenceType, ReferenceHit
from harpy.proc import run, which

DEFAULT_CAP = 20


class ReferenceSearcher(Protocol):
    def search(self, symbol: str, *, root: Path, cap: int = DEFAULT_CAP) -> list[ReferenceHit]: ...


def classify_hit(path: str, line: str, symbol: str) -> tuple[str, EvidenceType]:
    lowered = path.replace("\\", "/").lower()
    text = line.strip()
    if "test" in lowered or lowered.endswith("_test.py"):
        return "test", EvidenceType.TEST_REFERENCE
    if "import " in text and symbol.split(".")[-1] in text:
        return "import", EvidenceType.IMPORT
    if any(token in text for token in ("@app.", "route", "APIRouter", "FastAPI")):
        return "route", EvidenceType.ROUTE_MATCH
    if "worker" in lowered or "job" in lowered:
        return "worker", EvidenceType.STATIC_REFERENCE
    if any(part in lowered for part in ("config", "settings")):
        return "configuration", EvidenceType.STATIC_REFERENCE
    if symbol.split(".")[-1] in text:
        return "caller", EvidenceType.STATIC_REFERENCE
    return "unknown", EvidenceType.STATIC_REFERENCE


class RgSearcher:
    def search(self, symbol: str, *, root: Path, cap: int = DEFAULT_CAP) -> list[ReferenceHit]:
        needle = symbol.split(".")[-1]
        result = run(
            ["rg", "-n", "--no-heading", "-F", needle, str(root)],
            timeout=20,
        )
        if not result.ok:
            return []
        return _parse_rg(result.stdout, symbol=symbol, root=root, cap=cap)


class GitLsFilesSearcher:
    def search(self, symbol: str, *, root: Path, cap: int = DEFAULT_CAP) -> list[ReferenceHit]:
        listed = run(["git", "ls-files"], cwd=root, timeout=15)
        paths = listed.stdout.splitlines() if listed.ok else []
        if not paths:
            paths = [str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()]
        needle = symbol.split(".")[-1]
        hits: list[ReferenceHit] = []
        for rel in paths:
            path = root / rel
            if not path.is_file() or path.suffix not in {".py", ".ts", ".js", ".go", ".rs"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for index, line in enumerate(text.splitlines(), start=1):
                if needle in line:
                    kind, evidence = classify_hit(rel, line, symbol)
                    hits.append(
                        ReferenceHit(
                            symbol=symbol,
                            path=rel,
                            line=index,
                            kind=kind,
                            evidence=evidence,
                            snippet=line.strip()[:200],
                        )
                    )
                    if len(hits) >= cap:
                        return hits
        return hits


def _parse_rg(stdout: str, *, symbol: str, root: Path, cap: int) -> list[ReferenceHit]:
    hits: list[ReferenceHit] = []
    for raw in stdout.splitlines():
        if ":" not in raw:
            continue
        path_part, rest = raw.split(":", 1)
        if ":" not in rest:
            continue
        line_s, snippet = rest.split(":", 1)
        try:
            line_no = int(line_s)
        except ValueError:
            continue
        rel = os.path.relpath(path_part, root) if os.path.isabs(path_part) else path_part
        kind, evidence = classify_hit(rel, snippet, symbol)
        hits.append(
            ReferenceHit(
                symbol=symbol,
                path=rel,
                line=line_no,
                kind=kind,
                evidence=evidence,
                snippet=snippet.strip()[:200],
            )
        )
        if len(hits) >= cap:
            break
    return hits


def default_searcher() -> ReferenceSearcher:
    return RgSearcher() if which("rg") else GitLsFilesSearcher()


def find_references(
    symbols: list[str],
    *,
    root: Path,
    cap: int = DEFAULT_CAP,
    searcher: ReferenceSearcher | None = None,
) -> list[ReferenceHit]:
    backend = searcher or default_searcher()
    collected: list[ReferenceHit] = []
    for symbol in symbols:
        collected.extend(backend.search(symbol, root=root, cap=cap))
    return collected
