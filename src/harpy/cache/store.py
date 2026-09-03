from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from harpy import ANALYSIS_VERSION
from harpy.config import DEFAULT_CACHE_DIR
from harpy.models import AnalysisResult
from harpy.semantic.prompts import PROMPT_VERSION


def cache_key(
    *,
    repo: str,
    base_sha: str,
    head_sha: str,
    model: str,
    analysis_version: str = ANALYSIS_VERSION,
    prompt_version: str = PROMPT_VERSION,
    scope_signature: str = "",
) -> str:
    parts = [repo, base_sha, head_sha, analysis_version, prompt_version, model]
    if scope_signature:
        parts.append(scope_signature)
    material = "|".join(parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    safe = repo.replace("/", "_") or "repo"
    return f"{safe}/{base_sha[:8]}..{head_sha[:8]}.{digest}"


class CacheStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or DEFAULT_CACHE_DIR) / "analyses"

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> AnalysisResult | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            return AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError):
            return None

    def put(self, key: str, result: AnalysisResult) -> Path:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = result.model_dump_json(indent=2)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
        return path

    def clear(self) -> int:
        if not self.root.is_dir():
            return 0
        count = 0
        for path in self.root.rglob("*.json"):
            path.unlink()
            count += 1
        return count


def dumps_pretty(data: object) -> str:
    return json.dumps(data, indent=2, default=str)
