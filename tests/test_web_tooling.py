from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_installs_node_before_make_check() -> None:
    text = (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")
    assert "actions/setup-node@" in text
    assert 'node-version: "24"' in text
    assert "cache-dependency-path: web/package-lock.json" in text
    assert "postgresql" in text


def test_makefile_runs_web_checks() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "npm --prefix $(WEB) ci" in text
    assert "npm --prefix $(WEB) run lint" in text
    assert "npm --prefix $(WEB) run types" in text
    assert "npm --prefix $(WEB) run test" in text
    assert "fmt:check" in text


def test_dependabot_updates_npm() -> None:
    text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert "package-ecosystem: npm" in text
    assert "directory: /web" in text


def test_web_package_manifest_exists() -> None:
    assert (ROOT / "web" / "package.json").is_file()
    assert (ROOT / "web" / "src" / "theme-tokens.json").is_file()
    assert (ROOT / "docs" / "web" / "parity-checklist.md").is_file()
