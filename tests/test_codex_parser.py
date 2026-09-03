from __future__ import annotations

import json
from pathlib import Path

from harpy.semantic.parser import extract_json_text, parse_agent_stdout, parse_semantic

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cursor"


def test_extract_last_fence() -> None:
    text = 'intro\n```json\n{"pr_intent": "a", "changes": []}\n```\n'
    parsed = parse_semantic(text)
    assert parsed.pr_intent == "a"


def test_envelope_and_prose() -> None:
    inner = {"pr_intent": "x", "changes": []}
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(inner),
    }
    text, _ = parse_agent_stdout(json.dumps(envelope))
    parsed = parse_semantic(text)
    assert parsed.pr_intent == "x"


def test_recorded_success_envelope() -> None:
    raw = (FIXTURE / "success_envelope.json").read_text(encoding="utf-8")
    text, session = parse_agent_stdout(raw)
    assert session
    parsed = parse_semantic(text)
    assert parsed.changes


def test_balanced_object() -> None:
    blob = extract_json_text('noise {"pr_intent": "p", "changes": []} trailing')
    assert blob is not None
    assert "pr_intent" in blob
