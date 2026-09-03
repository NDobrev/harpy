from __future__ import annotations

from harpy.models import ChangedFile, DiffHunk, FileCategory, ReferenceHit, StaticSignals
from harpy.semantic.prompts import (
    MAX_HUNKS,
    MAX_REF_SNIPPET,
    MAX_REFERENCES,
    build_bundle,
    is_noise_file,
)


def _file(path: str, **scores: float) -> ChangedFile:
    category_scores = {category.value: 0.0 for category in FileCategory}
    category_scores.update(scores)
    return ChangedFile(
        path=path,
        status="modified",
        additions=1,
        deletions=0,
        category_scores=category_scores,
    )


def test_zero_lockfile_score_is_not_noise() -> None:
    file = _file("src/services/fees.ts", BUSINESS_LOGIC=0.55)
    assert "LOCKFILE" in file.category_scores
    assert file.category_scores["LOCKFILE"] == 0.0
    assert not is_noise_file(file)


def test_real_lockfile_is_noise() -> None:
    assert is_noise_file(_file("uv.lock", LOCKFILE=1.0))


def test_bundle_omits_noise_bodies_and_caps_hunks() -> None:
    files = [_file("uv.lock", LOCKFILE=1.0), _file("src/fees.ts", BUSINESS_LOGIC=0.55)]
    hunks = [
        DiffHunk(
            id=f"H{index}",
            file_path="src/fees.ts",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            patch=f"@@ hunk {index} @@\n+line\n",
            static_score=float(index),
        )
        for index in range(1, MAX_HUNKS + 11)
    ]
    hunks.append(
        DiffHunk(
            id="Hlock",
            file_path="uv.lock",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            patch="+should-not-appear\n",
            static_score=99,
        )
    )
    signals = [
        StaticSignals(
            file_path="src/fees.ts", hunk_id="H1", raw_score=1, categories=["BUSINESS_LOGIC"]
        )
    ]
    bundle = build_bundle(
        title="Fix fees",
        body="summary",
        files=files,
        hunks=hunks,
        signals=signals,
        references=[],
    )
    assert "uv.lock" in bundle
    assert "noise (omit body)" in bundle
    assert "+should-not-appear" not in bundle
    assert bundle.count("CHANGE H") == MAX_HUNKS
    assert f"(omitted {11} lower-score hunks)" in bundle
    assert "CHANGE H1 " not in bundle
    assert f"CHANGE H{MAX_HUNKS + 10} " in bundle


def test_bundle_trims_references() -> None:
    files = [_file("src/fees.ts", BUSINESS_LOGIC=0.55)]
    hunks = [
        DiffHunk(
            id="H1",
            file_path="src/fees.ts",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            patch="@@ hunk @@\n+line\n",
            static_score=1,
        )
    ]
    long = "x" * (MAX_REF_SNIPPET + 40)
    references = [
        ReferenceHit(symbol="fn", path="src/a.py", line=index, kind="caller", snippet=long)
        for index in range(1, MAX_REFERENCES + 8)
    ]
    bundle = build_bundle(
        title="Fix fees",
        body="summary",
        files=files,
        hunks=hunks,
        signals=[],
        references=references,
    )
    assert bundle.count("- fn caller") == MAX_REFERENCES
    assert long not in bundle
    assert "x" * MAX_REF_SNIPPET in bundle
