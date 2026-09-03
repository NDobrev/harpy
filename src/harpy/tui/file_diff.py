"""Full-file diff with per-change colors and jump targets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.text import Text

from harpy.models import AnalysisResult, DiffHunk, LogicalChange
from harpy.tui.change_tree import files_for_change

OTHER_COLORS = ("orange1", "dodger_blue2")


@dataclass(frozen=True)
class FileLine:
    prefix: str
    text: str
    hunk_id: str | None = None


@dataclass(frozen=True)
class DiffSection:
    kind: str
    change_id: str | None
    title: str
    current: bool
    text: Text
    gutter: str = ""
    accent: str = ""


def owner_for_hunk(changes: list[LogicalChange], hunk_id: str) -> LogicalChange | None:
    for change in changes:
        if hunk_id in (change.hunks or change.hunk_ids):
            return change
    return None


def other_color(change_id: str, other_ids: list[str]) -> str:
    if change_id not in other_ids:
        other_ids.append(change_id)
    return OTHER_COLORS[other_ids.index(change_id) % len(OTHER_COLORS)]


def read_workspace_file(result: AnalysisResult, relative: str) -> str:
    root = result.workspace_path
    if not root:
        return ""
    path = Path(root) / relative
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def stitch_file(after: str, hunks: list[DiffHunk]) -> list[FileLine]:
    after_lines = after.splitlines()
    ordered = sorted(hunks, key=lambda hunk: (hunk.new_start, hunk.id))
    out: list[FileLine] = []
    pos = 0
    for hunk in ordered:
        if after_lines:
            insert_at = min(max(hunk.new_start - 1, 0), len(after_lines))
            while pos < insert_at:
                out.append(FileLine(" ", after_lines[pos], None))
                pos += 1
        for raw in hunk.patch.splitlines():
            if raw.startswith("@@") or raw.startswith("+++") or raw.startswith("---"):
                continue
            if raw.startswith("\\"):
                continue
            if raw.startswith("+"):
                out.append(FileLine("+", raw[1:], hunk.id))
                if after_lines and pos < len(after_lines):
                    pos += 1
                continue
            if raw.startswith("-"):
                out.append(FileLine("-", raw[1:], hunk.id))
                continue
            body = raw[1:] if raw.startswith(" ") else raw
            out.append(FileLine(" ", body, hunk.id))
            if after_lines and pos < len(after_lines):
                pos += 1
    if after_lines:
        while pos < len(after_lines):
            out.append(FileLine(" ", after_lines[pos], None))
            pos += 1
    return out


def _line_style(prefix: str, *, current: bool, other: str | None) -> str:
    if prefix == " ":
        return "dim"
    if current:
        return "green" if prefix == "+" else "red"
    if other:
        return other
    return ""


def _render_lines(
    lines: list[FileLine],
    *,
    current_id: str | None,
    changes: list[LogicalChange],
    other_ids: list[str],
) -> list[DiffSection]:
    sections: list[DiffSection] = []
    buffer: list[FileLine] = []
    active_hunk: str | None = None

    def flush() -> None:
        nonlocal buffer, active_hunk
        if not buffer:
            return
        owner = owner_for_hunk(changes, active_hunk) if active_hunk else None
        current = bool(owner and owner.id == current_id)
        other = None if current or owner is None else other_color(owner.id, other_ids)
        text = Text()
        text.no_wrap = False
        accent = ""
        gutter = ""
        if owner is not None:
            tag = "current" if current else "other"
            accent = "green" if current else (other or "orange1")
            gutter = f"{tag}\n{owner.title}"
        for line in buffer:
            style = _line_style(line.prefix, current=current, other=other)
            body = f"{line.prefix}{line.text}\n"
            if style:
                text.append(body, style=style)
            else:
                text.append(body)
        sections.append(
            DiffSection(
                kind="change" if owner else "context",
                change_id=owner.id if owner else None,
                title=owner.title if owner else "",
                current=current,
                text=text,
                gutter=gutter,
                accent=accent,
            )
        )
        buffer = []
        active_hunk = None

    for line in lines:
        hunk = line.hunk_id
        group = hunk
        if buffer and group != active_hunk:
            flush()
        if not buffer:
            active_hunk = group
        buffer.append(line)
    flush()
    return sections


def annotated_file_sections(
    result: AnalysisResult,
    change: LogicalChange,
    *,
    file_path: str | None,
    changes: list[LogicalChange],
) -> list[DiffSection]:
    paths = [file_path] if file_path else files_for_change(change, result.hunks)
    if not paths:
        paths = list(
            dict.fromkeys(
                hunk.file_path
                for hunk in result.hunks
                if hunk.id in (change.hunks or change.hunk_ids)
            )
        )
    other_ids: list[str] = []
    sections: list[DiffSection] = []
    for path in paths:
        file_hunks = [hunk for hunk in result.hunks if hunk.file_path == path]
        if not file_hunks:
            continue
        header = Text()
        header.no_wrap = False
        header.append(f"{path}  [n/p] jump changes  [tab] panes\n", style="bold")
        sections.append(
            DiffSection(kind="header", change_id=None, title=path, current=False, text=header)
        )
        after = read_workspace_file(result, path)
        lines = stitch_file(after, file_hunks)
        sections.extend(
            _render_lines(lines, current_id=change.id, changes=changes, other_ids=other_ids)
        )
    if not sections:
        empty = Text("No file content for this change")
        empty.no_wrap = False
        sections.append(
            DiffSection(kind="header", change_id=None, title="", current=False, text=empty)
        )
    return sections
