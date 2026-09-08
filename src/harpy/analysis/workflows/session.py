"""Durable review-session records. No TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from harpy.models import AnalysisResult
from harpy.storage.catalog import BrowserCatalog
from harpy.storage.paths import data_home


@dataclass
class ReviewSession:
    review_id: UUID
    statuses: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    selected_id: str | None = None
    selected_file: str | None = None
    lens: str = "overview"
    focused_pane: str = "navigator"
    search: str = ""
    history: list[dict[str, object]] = field(default_factory=list)
    history_index: int = 0
    review_progress: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class OpenReview:
    result: AnalysisResult
    review_id: UUID


@dataclass(frozen=True)
class OpenInbox:
    repo: str
    number: int
    title: str = ""


def save_review_session(session: ReviewSession, *, root: Path | None = None) -> None:
    catalog = BrowserCatalog(root or data_home())
    catalog.put_session(session.review_id, _payload(session))
    entry = catalog.get_entry(session.review_id)
    if entry is not None and session.review_progress:
        catalog.put_entry(entry.model_copy(update={"review_progress": session.review_progress}))


def load_review_session(review_id: UUID, *, root: Path | None = None) -> ReviewSession | None:
    raw = BrowserCatalog(root or data_home()).get_session(review_id)
    if raw is None:
        return None
    return _from_payload(review_id, raw)


def _payload(session: ReviewSession) -> dict[str, object]:
    return {
        "review_id": str(session.review_id),
        "statuses": session.statuses,
        "notes": session.notes,
        "selected_id": session.selected_id,
        "selected_file": session.selected_file,
        "lens": session.lens,
        "focused_pane": session.focused_pane,
        "search": session.search,
        "history": session.history,
        "history_index": session.history_index,
        "review_progress": session.review_progress,
        "updated_at": session.updated_at,
    }


def _from_payload(review_id: UUID, raw: dict[str, object]) -> ReviewSession:
    statuses = raw.get("statuses")
    notes = raw.get("notes")
    history = raw.get("history")
    index = raw.get("history_index")
    return ReviewSession(
        review_id=review_id,
        statuses={str(key): str(value) for key, value in statuses.items()}
        if isinstance(statuses, dict)
        else {},
        notes={str(key): str(value) for key, value in notes.items()}
        if isinstance(notes, dict)
        else {},
        selected_id=str(raw["selected_id"]) if raw.get("selected_id") else None,
        selected_file=str(raw["selected_file"]) if raw.get("selected_file") else None,
        lens=str(raw.get("lens") or "overview"),
        focused_pane=str(raw.get("focused_pane") or "navigator"),
        search=str(raw.get("search") or ""),
        history=[item for item in history if isinstance(item, dict)]
        if isinstance(history, list)
        else [],
        history_index=index if isinstance(index, int) else 0,
        review_progress=str(raw.get("review_progress") or ""),
        updated_at=str(raw.get("updated_at") or ""),
    )
