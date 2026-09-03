from __future__ import annotations

from pathlib import Path

from harpy.cache.store import CacheStore, cache_key
from harpy.models import AnalysisResult, PullRequest


def test_cache_roundtrip(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    key = cache_key(
        repo="acme/app", base_sha="aaa111", head_sha="bbb222", model="cursor-grok-4.6-high-fast"
    )
    result = AnalysisResult(
        pr=PullRequest(
            number=1,
            title="t",
            body="",
            base_ref="main",
            head_ref="f",
            head_sha="bbb222",
            additions=1,
            deletions=0,
        )
    )
    store.put(key, result)
    loaded = store.get(key)
    assert loaded is not None
    assert loaded.pr.number == 1


def test_corrupt_cache_is_a_miss(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    key = cache_key(repo="acme/app", base_sha="aaa111", head_sha="bbb222", model="m")
    path = store.path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert store.get(key) is None


def test_model_changes_key() -> None:
    a = cache_key(repo="r", base_sha="a", head_sha="b", model="m1")
    b = cache_key(repo="r", base_sha="a", head_sha="b", model="m2")
    assert a != b
