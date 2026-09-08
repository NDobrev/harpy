from __future__ import annotations

import re
import tomllib
from importlib.metadata import version
from pathlib import Path

import harpy

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_project_metadata_is_the_version_source() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]

    assert harpy.__version__ == project_version
    assert version("harpy") == project_version
    package_init = (ROOT / "src" / "harpy" / "__init__.py").read_text(encoding="utf-8")
    assert '_distribution_version("harpy")' in package_init
    assert f'__version__ = "{project_version}"' not in package_init


def test_actions_are_pinned_to_commit_shas() -> None:
    for workflow in WORKFLOWS.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        refs = re.findall(r"uses:\s+[^@\s]+@([^\s#]+)", text)
        assert refs
        assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs)


def test_release_is_manual_validated_and_github_only() -> None:
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "RELEASE_VERSION: ${{ inputs.version }}" in text
    assert "refs/heads/main" in text
    assert "git show-ref --verify" in text
    assert "make check" in text
    assert "actions/attest@" in text
    assert "gh release create" in text
    assert "contents: write" in text
    assert "id-token: write" in text
    assert "attestations: write" in text
    assert "uv publish" not in text


def test_dependabot_updates_uv_and_actions() -> None:
    text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert "package-ecosystem: uv" in text
    assert "package-ecosystem: github-actions" in text
    assert text.count("interval: weekly") == 2
