"""Markdown, JSON, and self-contained HTML exports."""

from __future__ import annotations

import html
import json
from pathlib import Path

from harpy.models import AnalysisReport


def export_markdown(report: AnalysisReport, dest: Path) -> Path:
    dest.write_text(
        f"# Report {report.id}\n\nsnapshot: {report.snapshot_id}\n",
        encoding="utf-8",
    )
    return dest


def export_json(report: AnalysisReport, dest: Path) -> Path:
    dest.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return dest


def export_html(report: AnalysisReport, dest: Path) -> Path:
    title = html.escape(str(report.id))
    body = html.escape(json.dumps({"snapshot": str(report.snapshot_id)}))
    dest.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><style>body{font-family:sans-serif}</style>"
        f"</head><body><h1>{title}</h1><pre>{body}</pre></body></html>",
        encoding="utf-8",
    )
    return dest
