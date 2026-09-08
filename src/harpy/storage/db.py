"""Durable review store facade."""

from __future__ import annotations

from pathlib import Path

from harpy.storage.jsonstore import ReviewStore, SchemaTooNewError, StorageError


def migrate(path: Path) -> ReviewStore:
    return ReviewStore(path.parent)


__all__ = ["ReviewStore", "SchemaTooNewError", "StorageError", "migrate"]
