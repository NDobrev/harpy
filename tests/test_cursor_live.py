from __future__ import annotations

import json
from pathlib import Path

from harpy.semantic.parser import parse_agent_stdout


def test_replay_cleanliness_fixture() -> None:
    raw = (
        Path(__file__).resolve().parent / "fixtures" / "cursor" / "ask_json_cleanliness.json"
    ).read_text(encoding="utf-8")
    text, _ = parse_agent_stdout(raw)
    payload = json.loads(text)
    assert payload["ok"] is True
