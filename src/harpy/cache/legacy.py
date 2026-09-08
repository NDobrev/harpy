"""Import V1 JSON analyses as historical reports with legacy provenance."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from harpy.models import AnalysisReport, AnalysisResult, ReportProvenance
from harpy.storage.db import ReviewStore


def import_legacy_json(path: Path, store: ReviewStore) -> AnalysisReport | None:
    try:
        result = AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    report = AnalysisReport(
        id=uuid4(),
        snapshot_id=uuid4(),
        provenance=ReportProvenance(run_id=uuid4(), legacy=True),
    )
    store.put_report(report)
    del result
    return report
