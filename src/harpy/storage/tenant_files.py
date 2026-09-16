"""Tenant-partitioned content-addressed artifacts."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from harpy.storage.files import write_bytes


def tenant_artifact_dir(root: Path, tenant_id: UUID) -> Path:
    directory = (root / str(tenant_id)).resolve()
    root_resolved = root.resolve()
    if directory != root_resolved and root_resolved not in directory.parents:
        raise ValueError("artifact path escaped tenant root")
    return directory


def write_tenant_bytes(root: Path, tenant_id: UUID, payload: bytes) -> str:
    return write_bytes(tenant_artifact_dir(root, tenant_id), payload)


def read_tenant_bytes(root: Path, tenant_id: UUID, digest: str) -> bytes:
    if "/" in digest or "\\" in digest or digest in {".", ".."} or len(digest) != 64:
        raise ValueError("invalid artifact digest")
    path = tenant_artifact_dir(root, tenant_id) / digest
    if not path.is_file():
        raise FileNotFoundError(digest)
    return path.read_bytes()
