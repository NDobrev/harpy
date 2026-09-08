from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from harpy.cache.artifacts import (
    KIND_SEMANTIC,
    KIND_STATIC,
    ArtifactCache,
    ranking_key,
    semantic_key,
    static_key,
)
from harpy.cache.legacy import import_legacy_json
from harpy.models import AnalysisResult, PullRequest
from harpy.storage.db import ReviewStore


def test_static_cannot_satisfy_semantic_lookup(tmp_path: Path) -> None:
    cache = ArtifactCache(tmp_path)
    key = static_key(diff_digest="d", versions="1", config="c")
    cache.put(key, KIND_STATIC, b"static-only")
    assert cache.lookup_semantic(key) is None
    assert cache.get(key, expected_kind=KIND_STATIC) == b"static-only"


def test_scoring_change_does_not_change_semantic_key() -> None:
    semantic = semantic_key(
        scope="changes",
        model="cursor-grok-4.6-high-fast",
        prompt_version="12",
        intent_digest="intent",
        context_digest="ctx",
        dependency_digest="dep",
    )
    rank_a = ranking_key(input_digest="in", scoring_version="1")
    rank_b = ranking_key(input_digest="in", scoring_version="2")
    assert rank_a != rank_b
    assert semantic == semantic_key(
        scope="changes",
        model="cursor-grok-4.6-high-fast",
        prompt_version="12",
        intent_digest="intent",
        context_digest="ctx",
        dependency_digest="dep",
    )


def test_intent_change_invalidates_semantic_key() -> None:
    a = semantic_key(
        scope="changes",
        model="m",
        prompt_version="1",
        intent_digest="old",
        context_digest="c",
        dependency_digest="d",
    )
    b = semantic_key(
        scope="changes",
        model="m",
        prompt_version="1",
        intent_digest="new",
        context_digest="c",
        dependency_digest="d",
    )
    assert a != b


def test_cache_clean_preserves_reports_and_notes(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "data")
    report = store.put_empty_report(uuid4())
    store.add_note(uuid4(), "keep me")
    cache = ArtifactCache(tmp_path / "cache")
    cache.put("semantic:x", KIND_SEMANTIC, b"tmp")
    cache.clean()
    assert store.get_report(report.id) is not None
    store.close()


def test_legacy_import_is_not_a_semantic_hit(tmp_path: Path) -> None:
    path = tmp_path / "old.json"
    path.write_text(
        AnalysisResult(
            pr=PullRequest(
                number=1,
                title="t",
                body="",
                base_ref="main",
                head_ref="f",
                head_sha="abc",
                additions=0,
                deletions=0,
            )
        ).model_dump_json(),
        encoding="utf-8",
    )
    store = ReviewStore(tmp_path / "data")
    report = import_legacy_json(path, store)
    assert report is not None
    assert report.provenance.legacy is True
    store.close()
