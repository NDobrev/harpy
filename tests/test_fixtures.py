from __future__ import annotations

import tomllib
from pathlib import Path

from harpy.analysis.file_classifier import classify_path, primary_category
from harpy.analysis.static_signals import extract_signals
from harpy.models import ChangedFile, FileCategory, ScoringWeights

ROOT = Path(__file__).resolve().parent / "fixtures" / "repos"


def _expected(folder: Path) -> dict[str, list[str]]:
    data = tomllib.loads((folder / "expected.toml").read_text(encoding="utf-8"))
    return {str(key): list(value) for key, value in data.items()}


def test_fixture_rankings() -> None:
    weights = ScoringWeights()
    for folder in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        expected = _expected(folder)
        important = set(expected["important_files"])
        noise = set(expected.get("noise_files") or [])
        scored: list[tuple[float, str]] = []
        for file_path in folder.rglob("*"):
            if not file_path.is_file() or file_path.name == "expected.toml":
                continue
            rel = str(file_path.relative_to(folder)).replace("\\", "/")
            try:
                header = file_path.read_text(encoding="utf-8")[:200]
            except UnicodeDecodeError:
                continue
            file = ChangedFile(path=rel, status="modified", additions=1, deletions=0)
            file.category_scores = classify_path(rel, header=header)
            signals = extract_signals(file, weights)
            score = max((item.raw_score for item in signals), default=0)
            scored.append((score, rel))
            category = primary_category(file.category_scores)
            if rel in noise:
                assert category in {
                    FileCategory.GENERATED,
                    FileCategory.DOCUMENTATION,
                    FileCategory.LOCKFILE,
                    FileCategory.SNAPSHOT,
                }
        scored.sort(reverse=True)
        ranking = [path for _score, path in scored]
        for rel_path in important:
            assert rel_path in ranking
            if noise:
                assert ranking.index(rel_path) < max(
                    ranking.index(item) for item in noise if item in ranking
                )
