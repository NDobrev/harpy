"""Atomic content-addressed file writes."""

from __future__ import annotations

import os
import tempfile
from hashlib import sha256
from pathlib import Path


def write_bytes(directory: Path, payload: bytes) -> str:
    digest = sha256(payload).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / digest
    if dest.is_file():
        return digest
    fd, tmp_name = tempfile.mkstemp(prefix="harpy-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp_name).replace(dest)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return digest


def remove_orphan_temps(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    removed = 0
    for path in directory.glob("harpy-*.tmp"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed
