"""Authoritative storage-backend marker for migrated local roots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

MARKER_NAME = "storage-backend.json"
SCHEMA_GENERATION = 1
MIN_APP_VERSION = "0.1.0"
DATABASE_NAME = "harpy.sqlite3"
BACKEND_SQL = "sql"


class BackendError(RuntimeError):
    pass


class BackendIncompatibleError(BackendError):
    pass


@dataclass(frozen=True)
class BackendMarker:
    backend: str
    schema_generation: int
    import_id: UUID
    tenant_id: UUID
    actor_id: UUID
    min_app_version: str
    database: str

    def payload(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "schema_generation": self.schema_generation,
            "import_id": str(self.import_id),
            "tenant_id": str(self.tenant_id),
            "actor_id": str(self.actor_id),
            "min_app_version": self.min_app_version,
            "database": self.database,
        }


def marker_path(root: Path) -> Path:
    return root / MARKER_NAME


def database_file(root: Path, marker: BackendMarker | None = None) -> Path:
    name = marker.database if marker is not None else DATABASE_NAME
    return root / name


def read_marker(root: Path) -> BackendMarker | None:
    path = marker_path(root)
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackendError(f"storage backend marker is corrupt: {path}") from exc
    if not isinstance(loaded, dict):
        raise BackendError(f"storage backend marker is corrupt: {path}")
    try:
        marker = BackendMarker(
            backend=str(loaded["backend"]),
            schema_generation=int(str(loaded["schema_generation"])),
            import_id=UUID(str(loaded["import_id"])),
            tenant_id=UUID(str(loaded["tenant_id"])),
            actor_id=UUID(str(loaded["actor_id"])),
            min_app_version=str(loaded["min_app_version"]),
            database=str(loaded["database"]),
        )
    except (KeyError, ValueError) as exc:
        raise BackendError(f"storage backend marker is corrupt: {path}") from exc
    if marker.backend != BACKEND_SQL:
        raise BackendError(f"unknown storage backend {marker.backend}")
    if marker.schema_generation > SCHEMA_GENERATION:
        raise BackendIncompatibleError(
            f"database schema {marker.schema_generation} is newer than application "
            f"{SCHEMA_GENERATION}"
        )
    return marker


def write_marker(root: Path, marker: BackendMarker) -> None:
    path = marker_path(root)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(marker.payload(), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def is_sql_backend(root: Path) -> bool:
    return read_marker(root) is not None
