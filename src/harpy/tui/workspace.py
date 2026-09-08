"""Workspace navigation, search, palette, and review-state view models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from harpy.analysis.workflows.session import ReviewSession
from harpy.models import AnalysisResult, Freshness, LogicalChange, ReviewStatus
from harpy.tui.cards import FreshnessHeader, escape_plain, freshness_header
from harpy.tui.layout import WorkspaceLayout

LENSES = ("overview", "diff", "behavior", "tests", "impact", "questions", "omissions", "history")


@dataclass(frozen=True)
class PaletteAction:
    id: str
    title: str
    keys: str


PALETTE_ACTIONS: tuple[PaletteAction, ...] = (
    PaletteAction("scope", "Analyze", "s"),
    PaletteAction("expand", "Expand full diff", "e"),
    PaletteAction("impact", "Impact lens", "i"),
    PaletteAction("questions", "Questions lens", "r"),
    PaletteAction("tests", "Tests lens", "t"),
    PaletteAction("omissions", "Omissions / coverage", "o"),
    PaletteAction("search", "Search", "/"),
    PaletteAction("palette", "Command palette", "ctrl+p"),
    PaletteAction("collapse", "Collapse noise", "c"),
    PaletteAction("all", "Show all changes", "a"),
    PaletteAction("help", "Help", "?"),
    PaletteAction("zoom", "Maximize focused pane", "z"),
    PaletteAction("reviewed", "Mark reviewed", "v"),
    PaletteAction("reopen", "Reopen review", "shift+v"),
    PaletteAction("blocker", "Toggle blocker", "b"),
    PaletteAction("note", "Add note", "m"),
    PaletteAction("back", "Back", "escape"),
    PaletteAction("quit", "Quit", "q"),
)


@dataclass
class NavAnchor:
    change_id: str | None
    file_path: str | None
    lens: str
    scroll: int = 0


@dataclass
class WorkspaceState:
    selected_id: str | None
    selected_file: str | None = None
    lens: str = "overview"
    focused_pane: str = "navigator"
    maximized: bool = False
    inspector_open: bool = True
    search: str = ""
    statuses: dict[str, ReviewStatus] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    history: list[NavAnchor] = field(default_factory=list)
    history_index: int = -1
    freshness: Freshness = Freshness.UNKNOWN
    analyzed_rev: str = ""
    latest_rev: str = ""
    entering_text: bool = False

    def set_lens(self, lens: str) -> None:
        if lens not in LENSES:
            raise ValueError(lens)
        self.lens = lens
        self._commit()

    def select(self, change_id: str | None, file_path: str | None = None) -> None:
        self.selected_id = change_id
        self.selected_file = file_path
        self._commit()

    def apply_layout(self, layout: WorkspaceLayout) -> None:
        if layout.single_pane:
            self.inspector_open = self.focused_pane == "inspector"
        elif layout.inspector_drawer:
            self.inspector_open = self.focused_pane == "inspector"
        else:
            self.inspector_open = True

    def visible_panes(self, layout: WorkspaceLayout) -> tuple[str, ...]:
        if layout.single_pane:
            return (self.focused_pane,)
        if layout.inspector_drawer:
            if self.inspector_open:
                return ("navigator", "canvas", "inspector")
            return ("navigator", "canvas")
        return ("navigator", "canvas", "inspector")

    def cycle_pane(self, layout: WorkspaceLayout) -> str:
        panes = self.visible_panes(layout)
        if self.focused_pane not in panes:
            self.focused_pane = panes[0]
            return self.focused_pane
        index = panes.index(self.focused_pane)
        self.focused_pane = panes[(index + 1) % len(panes)]
        return self.focused_pane

    def mark(self, status: ReviewStatus) -> None:
        if self.selected_id is None:
            return
        if (
            status == ReviewStatus.BLOCKER
            and self.statuses.get(self.selected_id) == ReviewStatus.BLOCKER
        ):
            self.statuses[self.selected_id] = ReviewStatus.UNREVIEWED
            return
        self.statuses[self.selected_id] = status

    def add_note(self, text: str) -> None:
        if self.selected_id is None:
            return
        self.notes[self.selected_id] = text

    def back(self) -> NavAnchor | None:
        if self.history_index <= 0:
            return None
        self.history_index -= 1
        return self._restore(self.history[self.history_index])

    def forward(self) -> NavAnchor | None:
        if self.history_index + 1 >= len(self.history):
            return None
        self.history_index += 1
        return self._restore(self.history[self.history_index])

    def header(self, *, analyzed_at: str = "", checked: str = "") -> FreshnessHeader:
        return freshness_header(
            analyzed_rev=self.analyzed_rev or "unknown",
            analyzed_at=analyzed_at or "unknown",
            latest_rev=self.latest_rev or self.analyzed_rev or "unknown",
            checked=checked or "unknown",
            freshness=self.freshness,
        )

    def _commit(self) -> None:
        anchor = NavAnchor(self.selected_id, self.selected_file, self.lens)
        self.history = self.history[: self.history_index + 1]
        if self.history and self.history[self.history_index] == anchor:
            return
        self.history.append(anchor)
        self.history_index = len(self.history) - 1

    def _restore(self, anchor: NavAnchor) -> NavAnchor:
        self.selected_id = anchor.change_id
        self.selected_file = anchor.file_path
        self.lens = anchor.lens
        return anchor


def search_changes(
    changes: list[LogicalChange], query: str, notes: dict[str, str]
) -> list[LogicalChange]:
    needle = query.strip().lower()
    if not needle:
        return list(changes)

    def haystacks(change: LogicalChange) -> list[str]:
        return [
            change.id,
            change.title,
            *change.files,
            *change.affected_symbols,
            *change.review_questions,
            notes.get(change.id, ""),
            *change.possible_omissions,
        ]

    exact: list[LogicalChange] = []
    prefix: list[LogicalChange] = []
    substring: list[LogicalChange] = []
    for change in changes:
        texts = [item.lower() for item in haystacks(change) if item]
        if any(item == needle for item in texts):
            exact.append(change)
        elif any(item.startswith(needle) for item in texts):
            prefix.append(change)
        elif any(needle in item for item in texts):
            substring.append(change)
    return exact + prefix + substring


def inspector_card(
    change: LogicalChange | None,
    *,
    status: ReviewStatus,
    banner: str | None,
    head_sha: str = "",
) -> str:
    if change is None:
        return escape_plain(banner or "No logical change selected")
    evidence = snapshot_evidence_ref(change, head_sha=head_sha)
    action = {
        ReviewStatus.REVIEWED: "reviewed",
        ReviewStatus.QUESTION: "question open",
        ReviewStatus.BLOCKER: "blocker",
        ReviewStatus.UNREVIEWED: "unreviewed — v to mark",
    }[status]
    lines = [
        "BEHAVIOR",
        escape_plain(change.before or change.title or "(not assessed)"),
        "",
        "CONSEQUENCE",
        escape_plain(change.after or change.business_effect or change.why or "(not assessed)"),
        "",
        "EVIDENCE / LIMITATIONS",
        escape_plain(evidence),
        "",
        "ACTION",
        action,
        "",
        "Why this rank (expand)",
        f"importance {change.importance:.0f}  confidence {change.confidence:.0%}  risk {change.risk}",
    ]
    if banner:
        lines = [escape_plain(banner), ""] + lines
    if change.review_questions:
        lines.extend(
            ["", "QUESTIONS", *[f"• {escape_plain(item)}" for item in change.review_questions]]
        )
    if change.possible_omissions:
        lines.extend(
            ["", "OMISSIONS", *[f"• {escape_plain(item)}" for item in change.possible_omissions]]
        )
    if change.tests:
        lines.extend(["", "TESTS", *[f"• {escape_plain(item)}" for item in change.tests]])
    return "\n".join(lines)


def review_progress(
    changes: list[LogicalChange], statuses: dict[str, ReviewStatus]
) -> tuple[int, int]:
    reviewed = sum(1 for change in changes if statuses.get(change.id) == ReviewStatus.REVIEWED)
    return reviewed, len(changes)


def coverage_progress(result: AnalysisResult) -> tuple[int, int]:
    owned: set[str] = set()
    for change in result.changes:
        owned.update(change.hunk_ids or change.hunks)
    return len(owned), len(result.hunks)


def snapshot_evidence_ref(change: LogicalChange | None, *, head_sha: str) -> str:
    if change is None:
        return "none found within assessed context"
    raw = next(iter(change.files or change.hunk_ids or change.hunks), "")
    if not raw:
        return "none found within assessed context"
    path = raw.replace("\\", "/").lstrip("/")
    if path.startswith("/") or ".." in path.split("/"):
        return "unsupported source path — snapshot only"
    sha = (head_sha or "snapshot")[:12]
    return f"snapshot {sha}:{path}"


def lens_inspector(
    change: LogicalChange | None,
    *,
    lens: str,
    status: ReviewStatus,
    banner: str | None,
    notes: dict[str, str],
    history: list[NavAnchor],
    head_sha: str = "",
) -> str:
    if lens in {"overview", "diff", "impact"}:
        return inspector_card(change, status=status, banner=banner, head_sha=head_sha)
    heading, empty, items = _lens_items(change, lens=lens, notes=notes, history=history)
    body = "\n".join(f"• {escape_plain(item)}" for item in items) or empty
    lines = [heading, "", body]
    if banner:
        lines = [escape_plain(banner), ""] + lines
    return "\n".join(lines)


def _lens_items(
    change: LogicalChange | None,
    *,
    lens: str,
    notes: dict[str, str],
    history: list[NavAnchor],
) -> tuple[str, str, list[str]]:
    if change is None:
        return lens.upper(), "No logical change selected", []
    if lens == "questions":
        return "QUESTIONS", "none found within assessed context", list(change.review_questions)
    if lens == "tests":
        return "TESTS", "none found within assessed context", list(change.tests)
    if lens == "omissions":
        return "OMISSIONS", "none found within assessed context", list(change.possible_omissions)
    if lens == "behavior":
        return (
            "BEHAVIOR",
            "not assessed",
            [item for item in (change.before, change.after, change.why) if item],
        )
    if lens == "history":
        rows = [
            f"{item.change_id or '-'} · {item.lens} · {item.file_path or ''}" for item in history
        ]
        return "HISTORY", "none found within assessed context", rows
    note = notes.get(change.id, "")
    extra = [note] if note else []
    return lens.upper(), "not assessed", extra


def workspace_from_result(result: AnalysisResult) -> WorkspaceState:
    selected = result.changes[0].id if result.changes else None
    rev = (result.pr.head_sha or "")[:12]
    state = WorkspaceState(
        selected_id=selected,
        analyzed_rev=rev,
        latest_rev=rev,
        freshness=Freshness.UNKNOWN,
        history=[NavAnchor(selected, None, "overview")],
        history_index=0,
    )
    return state


def session_from_workspace(
    review_id: UUID, state: WorkspaceState, result: AnalysisResult
) -> ReviewSession:
    reviewed, total = review_progress(result.changes, state.statuses)
    return ReviewSession(
        review_id=review_id,
        statuses={key: value.value for key, value in state.statuses.items()},
        notes=dict(state.notes),
        selected_id=state.selected_id,
        selected_file=state.selected_file,
        lens=state.lens,
        focused_pane=state.focused_pane,
        search=state.search,
        history=[
            {
                "change_id": item.change_id,
                "file_path": item.file_path,
                "lens": item.lens,
                "scroll": item.scroll,
            }
            for item in state.history
        ],
        history_index=state.history_index,
        review_progress=f"{reviewed}/{total}",
        updated_at=datetime.now(UTC).isoformat(),
    )


def apply_session(state: WorkspaceState, session: ReviewSession, result: AnalysisResult) -> None:
    ids = {change.id for change in result.changes}
    restored: dict[str, ReviewStatus] = {}
    for key, raw in session.statuses.items():
        if key not in ids:
            continue
        try:
            restored[key] = ReviewStatus(raw)
        except ValueError:
            continue
    state.statuses = restored
    state.notes = {key: text for key, text in session.notes.items() if key in ids}
    if session.selected_id in ids:
        state.selected_id = session.selected_id
        state.selected_file = session.selected_file
    if session.lens in LENSES:
        state.lens = session.lens
    if session.focused_pane:
        state.focused_pane = session.focused_pane
    state.search = session.search
    history = [
        NavAnchor(
            change_id=str(item["change_id"]) if item.get("change_id") else None,
            file_path=str(item["file_path"]) if item.get("file_path") else None,
            lens=str(item.get("lens") or "overview"),
            scroll=int(str(item.get("scroll") or 0)),
        )
        for item in session.history
        if isinstance(item, dict)
    ]
    if history:
        state.history = history
        state.history_index = min(max(session.history_index, 0), len(history) - 1)
