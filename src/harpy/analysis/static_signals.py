"""Deterministic importance signals."""

from __future__ import annotations

import re

from harpy.analysis.file_classifier import primary_category
from harpy.models import ChangedFile, FileCategory, ScoringWeights, StaticSignals

AUTH_RE = re.compile(r"\b(auth|permission|rbac|is_admin|can_|authorize|role)\b", re.I)
API_RE = re.compile(r"\b(@app\.(route|get|post|put|delete)|APIRouter|FastAPI|@router\.)\b")
DB_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|session\.(add|delete|execute)|query\()\b", re.I)
ERROR_RE = re.compile(r"\b(raise |except |try:|catch )\b")
PUBLIC_RE = re.compile(r"^def [a-zA-Z]", re.M)


def extract_signals(file: ChangedFile, weights: ScoringWeights) -> list[StaticSignals]:
    category = primary_category(file.category_scores)
    results: list[StaticSignals] = []
    patches = [hunk.patch for hunk in file.hunks] or [""]
    combined = "\n".join(patches)
    base = StaticSignals(
        file_path=file.path,
        auth_change=bool(AUTH_RE.search(combined) or category is FileCategory.AUTH),
        api_change=bool(API_RE.search(combined) or category is FileCategory.API),
        db_change=bool(DB_RE.search(combined) or category is FileCategory.DATA),
        migration=category is FileCategory.MIGRATION,
        config_default=category is FileCategory.CONFIG and ("default" in combined.lower()),
        public_behavior=bool(PUBLIC_RE.search(combined))
        and category is FileCategory.BUSINESS_LOGIC,
        error_handling=bool(ERROR_RE.search(combined)),
        test_only=category is FileCategory.TEST,
        snapshot=category is FileCategory.SNAPSHOT,
        generated=category is FileCategory.GENERATED or file.generated_probability >= 0.8,
        lockfile=category is FileCategory.LOCKFILE,
        categories=[category.value],
    )
    if file.hunks:
        for hunk in file.hunks:
            signal = base.model_copy(update={"hunk_id": hunk.id})
            signal.raw_score = score_signals(signal, weights)
            hunk.static_score = signal.raw_score
            results.append(signal)
    else:
        base.raw_score = score_signals(base, weights)
        results.append(base)
    return results


def score_signals(signal: StaticSignals, weights: ScoringWeights) -> float:
    total = 0.0
    if signal.auth_change:
        total += weights.auth_change
    if signal.public_behavior:
        total += weights.public_behavior
    if signal.db_change:
        total += weights.db_change
    if signal.api_change:
        total += weights.api_change
    if signal.migration:
        total += weights.migration
    if signal.config_default:
        total += weights.config_default
    if signal.widely_referenced:
        total += weights.widely_referenced
    if signal.error_handling:
        total += weights.error_handling
    if signal.test_only:
        total += weights.test_only
    if signal.snapshot:
        total += weights.snapshot
    if signal.generated:
        total += weights.generated
    if signal.lockfile:
        total += weights.lockfile
    return total
