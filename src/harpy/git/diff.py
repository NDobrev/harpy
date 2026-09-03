"""Unified diff parser. Deterministic; no AI."""

from __future__ import annotations

import re

from harpy.models import ChangedFile, DiffHunk

_FILE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_OLD = re.compile(r"^--- (?:a/)?(.+)$")
_NEW = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_RENAME = re.compile(r"^rename from (.+)$")
_RENAME_TO = re.compile(r"^rename to (.+)$")


def parse_unified_diff(text: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    current: ChangedFile | None = None
    hunk_lines: list[str] = []
    hunk_meta: tuple[int, int, int, int] | None = None
    hunk_index = 0
    old_path = ""
    new_path = ""

    def flush_hunk() -> None:
        nonlocal hunk_lines, hunk_meta, hunk_index
        if current is None or hunk_meta is None:
            hunk_lines = []
            hunk_meta = None
            return
        hunk_index += 1
        old_start, old_count, new_start, new_count = hunk_meta
        patch = "\n".join(hunk_lines)
        adds = sum(1 for line in hunk_lines if line.startswith("+") and not line.startswith("+++"))
        dels = sum(1 for line in hunk_lines if line.startswith("-") and not line.startswith("---"))
        current.additions += adds
        current.deletions += dels
        current.hunks.append(
            DiffHunk(
                id=f"H{hunk_index}",
                file_path=current.path,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                patch=patch,
            )
        )
        hunk_lines = []
        hunk_meta = None

    def flush_file() -> None:
        nonlocal current
        flush_hunk()
        if current is not None:
            files.append(current)
        current = None

    for raw in text.splitlines():
        file_match = _FILE.match(raw)
        if file_match:
            flush_file()
            old_path, new_path = file_match.group(1), file_match.group(2)
            status = "modified"
            if old_path != new_path:
                status = "renamed"
            current = ChangedFile(
                path=new_path,
                status=status,
                additions=0,
                deletions=0,
                old_path=old_path if old_path != new_path else None,
            )
            continue
        if raw.startswith("new file"):
            if current:
                current.status = "added"
            continue
        if raw.startswith("deleted file"):
            if current:
                current.status = "deleted"
            continue
        if raw.startswith("Binary files") or raw.startswith("GIT binary patch"):
            if current:
                current.is_binary = True
            continue
        rename_from = _RENAME.match(raw)
        if rename_from and current:
            current.old_path = rename_from.group(1)
            current.status = "renamed"
            continue
        rename_to = _RENAME_TO.match(raw)
        if rename_to and current:
            current.path = rename_to.group(1)
            current.status = "renamed"
            continue
        old_match = _OLD.match(raw)
        if old_match:
            old_path = old_match.group(1)
            if old_path == "/dev/null" and current:
                current.status = "added"
            continue
        new_match = _NEW.match(raw)
        if new_match:
            new_path = new_match.group(1)
            if current and new_path != "/dev/null":
                current.path = new_path
            if new_path == "/dev/null" and current:
                current.status = "deleted"
            continue
        hunk_match = _HUNK.match(raw)
        if hunk_match:
            flush_hunk()
            hunk_meta = (
                int(hunk_match.group(1)),
                int(hunk_match.group(2) or "1"),
                int(hunk_match.group(3)),
                int(hunk_match.group(4) or "1"),
            )
            hunk_lines = [raw]
            continue
        if hunk_meta is not None:
            hunk_lines.append(raw)

    flush_file()
    return files
