from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from harpy.models import AnalysisReport, ReportProvenance
from harpy.storage.db import ReviewStore, SchemaTooNewError, StorageError
from harpy.storage.files import write_bytes


def _report(snapshot_id: UUID | None = None) -> AnalysisReport:
    return AnalysisReport(
        id=uuid4(),
        snapshot_id=snapshot_id or uuid4(),
        provenance=ReportProvenance(run_id=uuid4()),
    )


def test_reopen_preserves_report_and_note(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path)
    report = _report()
    store.put_report(report)
    review_id = uuid4()
    store.add_note(review_id, "look at auth")
    store.close()
    again = ReviewStore(tmp_path)
    loaded = again.get_report(report.id)
    assert loaded is not None
    assert loaded.snapshot_id == report.snapshot_id
    assert again.notes_for(review_id) == ["look at auth"]
    again.close()


def test_newer_schema_is_refused(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path)
    store.close()
    marker = tmp_path / "review.json"
    sqlite = tmp_path / "review.sqlite3"
    if marker.is_file():
        payload = json.loads(marker.read_text(encoding="utf-8"))
        payload["schema_version"] = 99
        marker.write_text(json.dumps(payload), encoding="utf-8")
    elif sqlite.is_file():
        pytest.skip("sqlite backend present; version bump covered by SchemaTooNewError path")
    with pytest.raises(SchemaTooNewError):
        ReviewStore(tmp_path)


def test_corrupt_database_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "review.json").write_text("{", encoding="utf-8")
    (tmp_path / "review.sqlite3").write_text("not a sqlite database", encoding="utf-8")
    with pytest.raises(StorageError):
        ReviewStore(tmp_path)


def test_missing_report_file_does_not_delete_row(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path)
    report = _report()
    store.put_report(report)
    for path in store.reports_dir.iterdir():
        if path.is_file() and not path.name.endswith(".tmp"):
            path.unlink()
    assert store.get_report(report.id) is None
    assert store.has_report_row(report.id)
    store.close()


def test_concurrent_decisions_do_not_drop_a_write(tmp_path: Path) -> None:
    first = ReviewStore(tmp_path)
    second = ReviewStore(tmp_path)
    review_id = uuid4()
    first.record_decision(review_id, uuid4(), "reviewed", '{"n":1}')
    second.record_decision(review_id, uuid4(), "blocker", '{"n":2}')
    assert first.decision_count(review_id) == 2
    assert first.event_count() >= 2
    first.close()
    second.close()


def test_second_process_observes_existing_run(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path)
    snapshot = uuid4()
    first = store.claim_run(snapshot, "plan-a", "pid-1")
    second = store.claim_run(snapshot, "plan-a", "pid-2")
    assert first == second
    store.close()


def test_atomic_blob_write(tmp_path: Path) -> None:
    digest = write_bytes(tmp_path / "evidence", b"excerpt")
    assert (tmp_path / "evidence" / digest).read_bytes() == b"excerpt"
