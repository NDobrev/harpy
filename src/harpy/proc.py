"""Sole subprocess chokepoint."""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("harpy.proc")

_SECRET = re.compile(r"(token|secret|password|authorization)=(\S+)", re.I)
_DEFAULT_CHUNK = 8192


@dataclass(frozen=True)
class ProcResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CancelToken:
    """Cooperative cancellation for a process group."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)


def redact(text: str) -> str:
    return _SECRET.sub(r"\1=<redacted>", text)


def _build_env(
    env: dict[str, str] | None,
    *,
    inherit_env: bool,
    env_allowlist: frozenset[str] | None,
) -> dict[str, str]:
    if inherit_env:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return merged
    allowed = env_allowlist or frozenset()
    merged = {key: os.environ[key] for key in allowed if key in os.environ}
    if env:
        merged.update(env)
    return merged


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return
    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except (ProcessLookupError, PermissionError, OSError):
            return
        time.sleep(0.02)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        return


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _bounded_read(handle: object, limit: int | None) -> str:
    chunks: list[bytes] = []
    total = 0
    read = getattr(handle, "read", None)
    if read is None:
        return ""
    while True:
        data = read(_DEFAULT_CHUNK)
        if not data:
            break
        if not isinstance(data, bytes):
            data = str(data).encode("utf-8", errors="replace")
        chunks.append(data)
        total += len(data)
        if limit is not None and total >= limit:
            break
    blob = b"".join(chunks)
    if limit is not None:
        blob = blob[:limit]
    return _decode(blob)


def run(
    argv: list[str] | tuple[str, ...],
    *,
    cwd: Path | str | None = None,
    timeout: float = 30.0,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
    inherit_env: bool = True,
    env_allowlist: frozenset[str] | None = None,
    cancel: CancelToken | None = None,
    max_output: int | None = None,
) -> ProcResult:
    if timeout <= 0:
        raise ValueError("timeout is required and must be positive")
    command = tuple(str(part) for part in argv)
    merged = _build_env(env, inherit_env=inherit_env, env_allowlist=env_allowlist)
    log.debug("run %s cwd=%s", command, cwd)
    cancelled = False
    timed_out = False
    stdout = ""
    stderr = ""
    returncode = -1
    try:
        with subprocess.Popen(
            command,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            env=merged,
            start_new_session=True,
        ) as proc:
            if stdin is not None and proc.stdin is not None:
                proc.stdin.write(stdin.encode("utf-8"))
                proc.stdin.close()
            out_box: list[str] = []
            err_box: list[str] = []
            readers = [
                threading.Thread(
                    target=lambda: out_box.append(_bounded_read(proc.stdout, max_output)),
                    daemon=True,
                ),
                threading.Thread(
                    target=lambda: err_box.append(_bounded_read(proc.stderr, max_output)),
                    daemon=True,
                ),
            ]
            for reader in readers:
                reader.start()
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                if cancel is not None and cancel.cancelled:
                    cancelled = True
                    _kill_group(proc.pid)
                    proc.wait(timeout=2)
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    _kill_group(proc.pid)
                    proc.wait(timeout=2)
                    break
                time.sleep(0.02)
            for reader in readers:
                reader.join(timeout=2)
            stdout = out_box[0] if out_box else ""
            stderr = err_box[0] if err_box else ""
            if proc.returncode is not None:
                returncode = proc.returncode
    except OSError as exc:
        result = ProcResult(argv=command, returncode=-1, stdout="", stderr=str(exc))
        if check:
            raise ProcError(result) from exc
        return result
    if cancelled:
        returncode = -2
        stderr = (stderr + "\ncancelled").strip()
    elif timed_out:
        returncode = -1
        extra = f"timed out after {timeout:.0f}s"
        stderr = f"{stderr}\n{extra}".strip() if stderr else extra
    result = ProcResult(argv=command, returncode=returncode, stdout=stdout, stderr=stderr)
    if check and not result.ok:
        raise ProcError(result)
    return result


class ProcError(RuntimeError):
    def __init__(self, result: ProcResult) -> None:
        self.result = result
        super().__init__(
            f"{result.argv[0]} exited {result.returncode}: {redact(result.stderr.strip())}"
        )


def which(name: str, env: Mapping[str, str] | None = None) -> Path | None:
    path = (env or os.environ).get("PATH", "")
    for folder in path.split(os.pathsep):
        candidate = Path(folder) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None
