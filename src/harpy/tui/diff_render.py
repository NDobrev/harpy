"""Color unified diffs so additions and removals are distinct."""

from __future__ import annotations

from rich.text import Text

from harpy.models import AnalysisResult, LogicalChange


def line_style(line: str) -> str:
    if line.startswith("+++ ") or line.startswith("--- "):
        return "bold"
    if line.startswith("@@"):
        return "cyan"
    if line.startswith("+"):
        return "green"
    if line.startswith("-"):
        return "red"
    return ""


def render_patch(patch: str) -> Text:
    text = Text()
    text.no_wrap = False
    for line in patch.splitlines():
        style = line_style(line)
        if style:
            text.append(line + "\n", style=style)
        else:
            text.append(line + "\n")
    return text


def render_change_diff(
    result: AnalysisResult,
    change: LogicalChange | None,
    *,
    expanded: bool,
    file_path: str | None = None,
) -> Text:
    text = Text()
    text.no_wrap = False
    if change is None:
        text.append("No change selected")
        return text
    active_file = None if expanded else file_path
    if active_file:
        header = f"{active_file}  [e] all files of this change  [tab] panes"
    else:
        header = (
            "THIS CHANGE  [e] file only  [tab] panes"
            if file_path
            else "THIS CHANGE  [tab] panes  [e] expand"
        )
    text.append(header + "\n\n", style="bold")
    hunk_ids = set(change.hunks or change.hunk_ids)
    change_files = set(change.files)
    found = False
    for hunk in result.hunks:
        if active_file and hunk.file_path != active_file:
            continue
        if hunk_ids:
            if hunk.id not in hunk_ids:
                continue
        elif change_files and hunk.file_path not in change_files:
            continue
        found = True
        text.append(f"--- {hunk.id} {hunk.file_path} ---\n", style="bold")
        text.append_text(render_patch(hunk.patch))
        text.append("\n")
    if not found:
        text.append("(no hunks for this change)")
    return text
