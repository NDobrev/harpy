from __future__ import annotations

import json

from typer.testing import CliRunner

from harpy.cli import app

runner = CliRunner()


def test_schema_web_emits_openapi() -> None:
    result = runner.invoke(app, ["schema", "--web"])
    assert result.exit_code == 0, result.output
    document = json.loads(result.output)
    assert document["openapi"] == "3.1.0"
    assert document["info"]["title"] == "Harpy Web API"
    assert "/api/v1/me" in document["paths"]
