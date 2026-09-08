"""GitHub CLI adapter."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from harpy.models import ChangedFile, PullRequest
from harpy.proc import ProcError, ProcResult, run

VIEW_FIELDS = (
    "number,title,body,commits,files,additions,deletions,"
    "baseRefName,headRefName,headRefOid,baseRefOid,url,state"
)


class GhError(RuntimeError):
    pass


_PR_URL = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")


def resolve_pr_ref(value: str) -> tuple[str | None, int | None]:
    """Return (repo, number). Either may be None ('.' means current PR)."""
    raw = value.strip()
    if raw in {".", ""}:
        return None, None
    if raw.isdigit():
        return None, int(raw)
    match = _PR_URL.search(raw)
    if match:
        return f"{match.group(1)}/{match.group(2)}", int(match.group(3))
    parsed = urlparse(raw)
    if parsed.scheme and "pull" in raw:
        raise GhError(f"unrecognized PR reference: {value}")
    return None, None


def _language_from_path(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    mapping = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".toml": "toml",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".md": "markdown",
        ".json": "json",
    }
    return mapping.get(suffix)


class GhProvider:
    def __init__(self, *, cwd: Path | None = None, timeout: float = 30.0) -> None:
        self.cwd = cwd
        self.timeout = timeout

    def _run(self, argv: list[str]) -> ProcResult:
        try:
            result = run(argv, cwd=self.cwd, timeout=self.timeout, check=False)
        except ProcError as exc:
            raise GhError(str(exc)) from exc
        if not result.ok:
            raise GhError(result.stderr.strip() or f"gh failed: {result.argv}")
        return result

    def current_repo(self) -> str:
        result = self._run(["gh", "repo", "view", "--json", "nameWithOwner"])
        data = json.loads(result.stdout)
        return str(data["nameWithOwner"])

    def get_pr(self, number: int | None, *, repo: str | None = None) -> PullRequest:
        argv = ["gh", "pr", "view"]
        if number is not None:
            argv.append(str(number))
        if repo:
            argv.extend(["--repo", repo])
        argv.extend(["--json", VIEW_FIELDS])
        data = json.loads(self._run(argv).stdout)
        return self._to_pr(data, repo=repo)

    def get_diff(self, number: int | None, *, repo: str | None = None) -> str:
        argv = ["gh", "pr", "diff"]
        if number is not None:
            argv.append(str(number))
        if repo:
            argv.extend(["--repo", repo])
        argv.append("--patch")
        return self._run(argv).stdout

    def _to_pr(self, data: dict[str, Any], *, repo: str | None) -> PullRequest:
        files: list[ChangedFile] = []
        for item in data.get("files") or []:
            path = str(item.get("path") or "")
            files.append(
                ChangedFile(
                    path=path,
                    status=str(item.get("status") or "modified"),
                    additions=int(item.get("additions") or 0),
                    deletions=int(item.get("deletions") or 0),
                    language=_language_from_path(path),
                )
            )
        url = str(data.get("url") or "")
        match = _PR_URL.search(url)
        resolved_repo = repo or (f"{match.group(1)}/{match.group(2)}" if match else "")
        return PullRequest(
            number=int(data["number"]),
            title=str(data.get("title") or ""),
            body=str(data.get("body") or ""),
            base_ref=str(data.get("baseRefName") or ""),
            head_ref=str(data.get("headRefName") or ""),
            head_sha=str(data.get("headRefOid") or ""),
            base_sha=str(data.get("baseRefOid") or ""),
            additions=int(data.get("additions") or 0),
            deletions=int(data.get("deletions") or 0),
            repo=resolved_repo,
            state=str(data.get("state") or "").lower(),
            files=files,
        )
