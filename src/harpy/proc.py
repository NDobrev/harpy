"""Sole subprocess chokepoint."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("harpy.proc")

_SECRET = re.compile(r"(token|secret|password|authorization)=(\S+)", re.I)


@dataclass(frozen=True)
class ProcResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def redact(text: str) -> str:
    return _SECRET.sub(r"\1=<redacted>", text)


def run(
    argv: list[str] | tuple[str, ...],
    *,
    cwd: Path | str | None = None,
    timeout: float = 30.0,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> ProcResult:
    if timeout <= 0:
        raise ValueError("timeout is required and must be positive")
    command = tuple(str(part) for part in argv)
    merged = os.environ.copy()
    if env:
        merged.update(env)
    log.debug("run %s cwd=%s", command, cwd)
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=merged,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = ProcResult(
            argv=command,
            returncode=-1,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=f"timed out after {timeout:.0f}s",
        )
        if check:
            raise ProcError(result) from exc
        return result
    result = ProcResult(
        argv=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and not result.ok:
        raise ProcError(result)
    return result


class ProcError(RuntimeError):
    def __init__(self, result: ProcResult) -> None:
        self.result = result
        super().__init__(
            f"{result.argv[0]} exited {result.returncode}: {redact(result.stderr.strip())}"
        )


def which(name: str, env: dict[str, str] | None = None) -> Path | None:
    path = (env or os.environ).get("PATH", "")
    for folder in path.split(os.pathsep):
        candidate = Path(folder) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None
