"""Independently keyed recomputable artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import time

from harpy.storage.files import write_bytes
from harpy.storage.paths import cache_home

DEFAULT_LIMIT = 5 * 1024 * 1024 * 1024
KIND_SOURCE = "source"
KIND_SYNTAX = "syntax"
KIND_STATIC = "static"
KIND_SEMANTIC = "semantic"
KIND_RANKING = "ranking"


def artifact_key(*, kind: str, parts: list[str]) -> str:
    material = "|".join([kind, *parts])
    return f"{kind}:{sha256(material.encode('utf-8')).hexdigest()}"


def source_key(*, repository: str, blob_hash: str) -> str:
    return artifact_key(kind=KIND_SOURCE, parts=[repository, blob_hash])


def syntax_key(*, language: str, grammar: str, query: str, content_hash: str) -> str:
    return artifact_key(kind=KIND_SYNTAX, parts=[language, grammar, query, content_hash])


def static_key(*, diff_digest: str, versions: str, config: str) -> str:
    return artifact_key(kind=KIND_STATIC, parts=[diff_digest, versions, config])


def semantic_key(
    *,
    scope: str,
    model: str,
    prompt_version: str,
    intent_digest: str,
    context_digest: str,
    dependency_digest: str,
    options: str = "",
) -> str:
    return artifact_key(
        kind=KIND_SEMANTIC,
        parts=[
            scope,
            model,
            prompt_version,
            intent_digest,
            context_digest,
            dependency_digest,
            options,
        ],
    )


def ranking_key(*, input_digest: str, scoring_version: str) -> str:
    return artifact_key(kind=KIND_RANKING, parts=[input_digest, scoring_version])


@dataclass
class ArtifactMeta:
    key: str
    kind: str
    size: int
    last_access: float
    digest: str = ""
    invalidation: str = ""


class ArtifactCache:
    def __init__(self, root: Path | None = None, *, limit: int = DEFAULT_LIMIT) -> None:
        self.root = (root or cache_home()) / "artifacts"
        self.index_path = self.root / "index.json"
        self.limit = limit
        self.active: set[str] = set()
        self.root.mkdir(parents=True, exist_ok=True)

    def _index(self) -> dict[str, ArtifactMeta]:
        if not self.index_path.is_file():
            return {}
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        items: dict[str, ArtifactMeta] = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(value, dict):
                    items[str(key)] = ArtifactMeta(
                        key=str(key),
                        kind=str(value.get("kind") or ""),
                        size=int(value.get("size") or 0),
                        last_access=float(value.get("last_access") or 0),
                        digest=str(value.get("digest") or ""),
                        invalidation=str(value.get("invalidation") or ""),
                    )
        return items

    def _save(self, items: dict[str, ArtifactMeta]) -> None:
        payload = {
            key: {
                "kind": item.kind,
                "size": item.size,
                "last_access": item.last_access,
                "digest": item.digest,
                "invalidation": item.invalidation,
            }
            for key, item in items.items()
        }
        self.index_path.write_text(json.dumps(payload), encoding="utf-8")

    def put(self, key: str, kind: str, payload: bytes) -> str:
        digest = write_bytes(self.root / kind, payload)
        items = self._index()
        items[key] = ArtifactMeta(
            key=key, kind=kind, size=len(payload), last_access=time(), digest=digest
        )
        self._save(items)
        self._evict(items)
        return digest

    def get(self, key: str, *, expected_kind: str | None = None) -> bytes | None:
        items = self._index()
        meta = items.get(key)
        if meta is None:
            return None
        if expected_kind is not None and meta.kind != expected_kind:
            return None
        path = self.root / meta.kind / meta.digest
        if not path.is_file():
            return None
        meta.last_access = time()
        self._save(items)
        return path.read_bytes()

    def lookup_semantic(self, key: str) -> bytes | None:
        return self.get(key, expected_kind=KIND_SEMANTIC)

    def stats(self) -> dict[str, int]:
        items = self._index()
        return {
            "count": len(items),
            "bytes": sum(item.size for item in items.values()),
        }

    def explain(self, key: str) -> ArtifactMeta | None:
        return self._index().get(key)

    def clean(self) -> int:
        items = self._index()
        removed = 0
        for key, meta in list(items.items()):
            if key in self.active:
                continue
            folder = self.root / meta.kind
            if folder.is_dir():
                for path in folder.iterdir():
                    if path.is_file():
                        path.unlink()
                        removed += 1
            del items[key]
        self._save(items)
        return removed

    def _evict(self, items: dict[str, ArtifactMeta]) -> None:
        total = sum(item.size for item in items.values())
        if total <= self.limit:
            return
        ordered = sorted(
            (item for item in items.values() if item.key not in self.active),
            key=lambda item: item.last_access,
        )
        for meta in ordered:
            if total <= self.limit:
                break
            folder = self.root / meta.kind
            for path in folder.glob("*"):
                if path.is_file():
                    path.unlink(missing_ok=True)
            total -= meta.size
            del items[meta.key]
        self._save(items)
