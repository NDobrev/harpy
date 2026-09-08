"""XDG/home-directory locations for durable state and cache."""

from __future__ import annotations

import os
from pathlib import Path

from harpy.config import DEFAULT_CACHE_DIR


def data_home() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "harpy"
    return Path.home() / ".local" / "share" / "harpy"


def cache_home() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "harpy"
    return DEFAULT_CACHE_DIR


def config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "harpy"
    return Path.home() / ".config" / "harpy"


def database_path(root: Path | None = None) -> Path:
    return (root or data_home()) / "review.sqlite3"
