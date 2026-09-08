from __future__ import annotations

from typer.testing import CliRunner

from harpy.cli import app, rewrite_argv
from harpy.config import DEFAULT_MODEL

runner = CliRunner()


def test_doctor_json(fake_gh_path: object) -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    assert DEFAULT_MODEL in result.output
    assert "model_source" in result.output


def test_schema_command() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    assert "SemanticAnalysisResult" in result.output or "pr_intent" in result.output


def test_rewrite_inserts_review_before_flags() -> None:
    assert rewrite_argv(["1842"]) == ["review", "1842"]
    assert rewrite_argv(["--repo", "owner/name", "1842"]) == [
        "review",
        "--repo",
        "owner/name",
        "1842",
    ]
    assert rewrite_argv(["doctor", "--json"]) == ["doctor", "--json"]
    assert rewrite_argv(["analyze", "1842", "--static"]) == ["analyze", "1842", "--static"]
    assert rewrite_argv(["--help"]) == ["--help"]
    assert rewrite_argv([]) == ["browse"]
