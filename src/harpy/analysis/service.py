"""Application facade for opening, analyzing, and querying reviews."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from harpy.analysis.pipeline import analyze_static, apply_semantic
from harpy.analysis.workflows.acquire import source_for
from harpy.analysis.workflows.browser import list_browser, load_analysis, persist_analysis
from harpy.analysis.workflows.events import make_event, should_apply_event
from harpy.config import HarpyConfig
from harpy.git.source import SourceRead
from harpy.models import (
    AnalysisPlan,
    AnalysisResult,
    BrowserItem,
    ProgressEvent,
    ReviewTarget,
    RevisionSnapshot,
    RunHandle,
    RunStatus,
    ScopeCall,
)
from harpy.proc import CancelToken

ProgressSink = Callable[[ProgressEvent], None]


class ReviewService:
    """Coordinate opening, refreshing, analyzing, and querying reviews."""

    def __init__(self, config: HarpyConfig) -> None:
        self.config = config
        self._lock = Lock()
        self._runs: dict[UUID, RunHandle] = {}
        self._cancels: dict[UUID, CancelToken] = {}
        self._results: dict[UUID, AnalysisResult] = {}
        self._sequences: dict[UUID, int] = {}

    def open_review(
        self,
        target: str | ReviewTarget,
        *,
        repo: str | None = None,
        cwd: Path | None = None,
        use_cache: bool = True,
        progress: ProgressSink | None = None,
    ) -> AnalysisResult:
        ref = target.local_comparison if isinstance(target, ReviewTarget) else target
        if isinstance(target, ReviewTarget) and target.pr_number is not None:
            ref = str(target.pr_number)
        review_id = uuid4()
        result = analyze_static(
            str(ref),
            config=self.config,
            repo=repo,
            cwd=cwd,
            use_ai=True,
            use_cache=use_cache,
            progress=self._string_progress(review_id, progress),
        )
        self._results[review_id] = result
        persist_analysis(result)
        return result

    def start_analysis(
        self,
        result: AnalysisResult,
        *,
        review_id: UUID | None = None,
        plan: list[ScopeCall] | None = None,
        scope_signature: str = "",
        use_cache: bool = True,
        progress: ProgressSink | None = None,
    ) -> tuple[RunHandle, AnalysisResult]:
        review = review_id or uuid4()
        run_id = uuid4()
        snapshot_id = uuid4()
        handle = RunHandle(
            run_id=run_id,
            review_id=review,
            snapshot_id=snapshot_id,
            status=RunStatus.RUNNING,
        )
        token = CancelToken()
        with self._lock:
            self._runs[run_id] = handle
            self._cancels[run_id] = token
            self._sequences[run_id] = 0
        self._emit(
            progress,
            run_id=run_id,
            review_id=review,
            snapshot_id=snapshot_id,
            status=RunStatus.RUNNING,
            message="Starting analysis",
        )
        updated = apply_semantic(
            result,
            config=self.config,
            plan=plan,
            force=True,
            use_cache=use_cache,
            progress=self._string_progress(
                review, progress, run_id=run_id, snapshot_id=snapshot_id
            ),
            scope_signature=scope_signature,
        )
        status = RunStatus.PARTIAL if updated.banner else RunStatus.COMPLETED
        if token.cancelled:
            status = RunStatus.CANCELLED
        handle = RunHandle(run_id=run_id, review_id=review, snapshot_id=snapshot_id, status=status)
        with self._lock:
            self._runs[run_id] = handle
            self._results[review] = updated
        self._emit(
            progress,
            run_id=run_id,
            review_id=review,
            snapshot_id=snapshot_id,
            status=status,
            message="Analysis finished",
        )
        persist_analysis(updated)
        return handle, updated

    def list_reviews(self, tab: str = "local", *, offline: bool = False) -> list[BrowserItem]:
        return list_browser(tab, offline=offline)

    def select_report(self, review_id: UUID) -> AnalysisResult | None:
        return load_analysis(review_id)

    def cancel_analysis(self, run_id: UUID) -> RunStatus:
        with self._lock:
            token = self._cancels.get(run_id)
            handle = self._runs.get(run_id)
        if token is not None:
            token.cancel()
        if handle is None:
            return RunStatus.CANCELLED
        updated = RunHandle(
            run_id=handle.run_id,
            review_id=handle.review_id,
            snapshot_id=handle.snapshot_id,
            status=RunStatus.CANCELLED,
        )
        with self._lock:
            self._runs[run_id] = updated
        return RunStatus.CANCELLED

    def get_run(self, run_id: UUID) -> RunStatus:
        with self._lock:
            handle = self._runs.get(run_id)
        return handle.status if handle is not None else RunStatus.FAILED

    def plan_analysis(self, review_id: UUID, *, full: bool = False, digest: str) -> AnalysisPlan:
        return AnalysisPlan(
            id=uuid4(), review_id=review_id, snapshot_id=uuid4(), full=full, digest=digest
        )

    def get_source(
        self,
        path: str,
        *,
        side: str = "head",
        snapshot: RevisionSnapshot | None = None,
        root: Path | None = None,
        repo: Path | None = None,
    ) -> SourceRead:
        return source_for(snapshot=snapshot, root=root, repo=repo, path=path, side=side)

    def accept_event(
        self,
        event: ProgressEvent,
        *,
        review_id: UUID,
        run_id: UUID,
        min_sequence: int = -1,
    ) -> bool:
        return should_apply_event(
            event, review_id=review_id, run_id=run_id, min_sequence=min_sequence
        )

    def _string_progress(
        self,
        review_id: UUID,
        sink: ProgressSink | None,
        *,
        run_id: UUID | None = None,
        snapshot_id: UUID | None = None,
    ) -> Callable[[str], None] | None:
        if sink is None:
            return None
        active_run = run_id or uuid4()
        snapshot = snapshot_id or uuid4()

        def emit(message: str) -> None:
            self._emit(
                sink,
                run_id=active_run,
                review_id=review_id,
                snapshot_id=snapshot,
                status=RunStatus.RUNNING,
                message=message,
            )

        return emit

    def _emit(
        self,
        sink: ProgressSink | None,
        *,
        run_id: UUID,
        review_id: UUID,
        snapshot_id: UUID,
        status: RunStatus,
        message: str,
    ) -> None:
        with self._lock:
            sequence = self._sequences.get(run_id, 0) + 1
            self._sequences[run_id] = sequence
        event = make_event(
            run_id=run_id,
            review_id=review_id,
            snapshot_id=snapshot_id,
            sequence=sequence,
            status=status,
            message=message,
        )
        if sink is not None:
            sink(event)
