from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from harpy.proc import CancelToken, ProcResult, run


def test_timeout_returns_result_instead_of_raising() -> None:
    result = run(["sleep", "2"], timeout=0.2)
    assert not result.ok
    assert result.returncode == -1
    assert "timed out after" in result.stderr


def test_cancel_kills_process_and_child(tmp_path: Path) -> None:
    marker = tmp_path / "child.pid"
    script = tmp_path / "parent.sh"
    script.write_text(
        f"#!/bin/sh\nsleep 60 &\necho $! > {marker}\nwait\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    token = CancelToken()
    box: dict[str, ProcResult] = {}

    def go() -> None:
        box["result"] = run([str(script)], timeout=15, cancel=token)

    thread = threading.Thread(target=go)
    thread.start()
    pid = 0
    for _ in range(80):
        if marker.exists() and marker.read_text(encoding="utf-8").strip().isdigit():
            pid = int(marker.read_text(encoding="utf-8").strip())
            break
        time.sleep(0.05)
    assert pid > 0
    token.cancel()
    thread.join(5)
    assert not thread.is_alive()
    assert box["result"].returncode == -2
    time.sleep(0.1)
    try:
        os.kill(pid, 0)
        alive = True
    except OSError:
        alive = False
    assert not alive


def test_allowlisted_env_does_not_inherit_home() -> None:
    result = run(
        ["/usr/bin/env"],
        inherit_env=False,
        env={"HARPY_TEST_FLAG": "1"},
        env_allowlist=frozenset(),
        timeout=5,
    )
    assert result.ok
    assert "HARPY_TEST_FLAG=1" in result.stdout
    assert "HOME=" not in result.stdout


def test_max_output_truncates_stdout() -> None:
    result = run(["python3", "-c", "print('x' * 4000)"], timeout=5, max_output=80)
    assert result.ok
    assert len(result.stdout.encode("utf-8")) <= 80
