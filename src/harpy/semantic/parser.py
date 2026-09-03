"""Tolerant extraction of SemanticAnalysisResult from cursor-agent output."""

from __future__ import annotations

import json
import re
from typing import Any

from harpy.models import SemanticAnalysisResult

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json_text(text: str) -> str | None:
    fences = list(_FENCE.finditer(text))
    if fences:
        return fences[-1].group(1)
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for index, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_agent_stdout(stdout: str) -> tuple[str, str]:
    """Return (result_text, session_id) from --output-format json envelope or raw text."""
    stripped = stdout.strip()
    try:
        payload: Any = json.loads(stripped)
    except json.JSONDecodeError:
        return stdout, ""
    if isinstance(payload, dict) and payload.get("type") == "result":
        return str(payload.get("result") or ""), str(payload.get("session_id") or "")
    if isinstance(payload, dict) and "changes" in payload:
        return json.dumps(payload), ""
    return stdout, ""


def parse_semantic(text: str) -> SemanticAnalysisResult:
    blob = extract_json_text(text)
    if blob is None:
        raise ValueError("no JSON object in agent output")
    data = json.loads(blob)
    return SemanticAnalysisResult.model_validate(data)
