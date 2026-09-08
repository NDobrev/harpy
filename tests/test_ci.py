from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"
MAKEFILE = ROOT / "Makefile"


def test_ci_workflow_is_the_acceptance_gate() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "make setup" in text
    assert "make check" in text
    assert 'python-version: "3.12"' in text
    assert "astral-sh/setup-uv@v10.0.1" in text
    assert "cursor-agent" not in text
    assert "--force" not in text


def test_ci_install_and_fmt_do_not_rewrite() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "ifeq ($(CI),true)" in text
    assert "--frozen" in text
    assert "format --check" in text or "FORMAT_ARGS := --check" in text
    assert '-m "not cursor"' in text
