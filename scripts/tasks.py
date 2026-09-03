#!/usr/bin/env python3
"""Print the agent-readable task queue from docs/tasks/*.md."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = ROOT / "docs" / "tasks"
FRONT = re.compile(r"^---\n(.*?)\n---", re.S)


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONT.match(text)
    if not match:
        return {}
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("\"'")
    return data


def load_tasks() -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for path in sorted(TASK_DIR.glob("HP-*.md")):
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        meta["path"] = str(path.relative_to(ROOT))
        tasks.append(meta)
    return tasks


def depends(task: dict[str, str]) -> list[str]:
    raw = task.get("depends_on", "").strip()
    if not raw or raw in {"[]", "none", "-"}:
        return []
    raw = raw.strip("[]")
    return [part.strip().strip("\"'") for part in raw.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", action="store_true", help="only todo tasks with done deps")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    tasks = load_tasks()
    by_id = {t.get("id", ""): t for t in tasks}

    selected: list[dict[str, str]] = []
    for task in tasks:
        if args.ready:
            if task.get("status") != "todo":
                continue
            if any(by_id.get(dep, {}).get("status") != "done" for dep in depends(task)):
                continue
        selected.append(task)

    if not selected:
        print("no tasks")
        return 0
    for task in selected:
        print(f"{task.get('id', '?'):8} {task.get('status', '?'):6} {task.get('path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
