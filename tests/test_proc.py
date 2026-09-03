from __future__ import annotations

from harpy.proc import run


def test_timeout_returns_result_instead_of_raising() -> None:
    result = run(["sleep", "2"], timeout=0.2)
    assert not result.ok
    assert result.returncode == -1
    assert "timed out after" in result.stderr
