"""Static fallback for endpoint/API contract changes. No diagrams — the agent decides those."""

from __future__ import annotations

import re

from harpy.models import AnalysisResult, ApiEndpointImpact, DiffHunk, FileCategory

_METHOD_PATH = re.compile(
    r"""(?ix)
    (?:
        @?(?:app|router)\.(get|post|put|patch|delete|head|options)\(\s*["']([^"']+)["']
        | \b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s"'`]+)
        | ["'`](/v\d+/[^"'`\s]+)["'`]
    )
    """
)
_DELETED_ROUTE = re.compile(
    r"""(?ixm)^\s*-\s*.*(?:
        @?(?:app|router)\.(get|post|put|patch|delete)
        | \b(?:GET|POST|PUT|PATCH|DELETE)\s+/
        | ["'`]/v\d+/
    )"""
)


def looks_like_api(result: AnalysisResult) -> bool:
    if any(signal.api_change for signal in result.signals):
        return True
    return any(
        file.category_scores.get(FileCategory.API, 0.0) >= 0.5
        or "/routes/" in file.path
        or file.path.endswith("routes.ts")
        for file in result.files
    )


def extract_static_api_impacts(result: AnalysisResult) -> list[ApiEndpointImpact]:
    if not looks_like_api(result):
        return []
    seen: dict[tuple[str, str], ApiEndpointImpact] = {}
    for hunk in result.hunks:
        if not _hunk_is_api(result, hunk):
            continue
        breaking = bool(_DELETED_ROUTE.search(hunk.patch))
        for method, path in _routes_in(hunk.patch):
            key = (method, path)
            if key in seen:
                if breaking:
                    seen[key].breaking = True
                    seen[
                        key
                    ].breaking_reason = "a route definition was removed or rewritten in the diff"
                if hunk.file_path and hunk.file_path not in seen[key].files:
                    seen[key].files.append(hunk.file_path)
                continue
            change_id = _change_id_for(result, hunk.id)
            seen[key] = ApiEndpointImpact(
                change_id=change_id,
                method=method,
                path=path,
                summary=f"{method} {path}".strip(),
                before="",
                after="",
                impact="Static extraction only — wait for semantic analysis for behavior and diagrams.",
                breaking=breaking,
                breaking_reason=(
                    "a route definition was removed or rewritten in the diff" if breaking else ""
                ),
                files=[hunk.file_path] if hunk.file_path else [],
            )
    return list(seen.values())


def _hunk_is_api(result: AnalysisResult, hunk: DiffHunk) -> bool:
    for signal in result.signals:
        if signal.hunk_id == hunk.id and signal.api_change:
            return True
    for file in result.files:
        if file.path == hunk.file_path and file.category_scores.get(FileCategory.API, 0.0) >= 0.5:
            return True
    return "/routes/" in hunk.file_path or "routes.ts" in hunk.file_path


def _routes_in(patch: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for match in _METHOD_PATH.finditer(patch):
        method = (match.group(1) or match.group(3) or "ANY").upper()
        path = match.group(2) or match.group(4) or match.group(5) or ""
        if path:
            found.append((method, path))
    return found


def _change_id_for(result: AnalysisResult, hunk_id: str) -> str:
    for change in result.changes:
        if hunk_id in (change.hunks or change.hunk_ids):
            return change.id
    return ""
