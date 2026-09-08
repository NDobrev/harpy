"""Orchestrates fetch → static → optional semantic → score → cache."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol

from harpy.analysis.api_impact import extract_static_api_impacts
from harpy.analysis.db_impact import extract_static_db_impacts
from harpy.analysis.diagrams.tree import attach_blast_trees
from harpy.analysis.file_classifier import apply_classification, primary_category
from harpy.analysis.impact_scope import enrich_contract_impacts
from harpy.analysis.references import find_references
from harpy.analysis.scoring import score_change
from harpy.analysis.semantic_merge import merge_semantic
from harpy.analysis.static_signals import extract_signals, score_signals
from harpy.analysis.symbols import read_source, symbols_for_hunk
from harpy.analysis.syntax.extract import extract_file_facts, symbols_from_facts
from harpy.analysis.syntax.imports import filter_hits
from harpy.analysis.workflows.session import OpenInbox, OpenReview, ReviewSession
from harpy.cache.store import CacheStore, cache_key
from harpy.config import HarpyConfig, with_model
from harpy.git.diff import parse_unified_diff
from harpy.git.worktree import WorktreeManager
from harpy.github.gh import GhProvider, resolve_pr_ref
from harpy.models import (
    AnalysisResult,
    BrowserItem,
    FileFacts,
    LogicalChange,
    PullRequest,
    ScopeCall,
    SemanticAnalysisResult,
    SemanticChangeDraft,
    StaticSignals,
)
from harpy.semantic.client import DEGRADED_BANNER, CursorAgentClient
from harpy.semantic.facts import write_symbol_facts
from harpy.semantic.prompts import bundle_from_result

ProgressCallback = Callable[[str], None]


class SemanticAnalyzer(Protocol):
    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult: ...


def _note(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _static_drafts(result: AnalysisResult) -> list[SemanticChangeDraft]:
    drafts: list[SemanticChangeDraft] = []
    for index, file in enumerate(result.files, start=1):
        hunk_ids = [hunk.id for hunk in file.hunks]
        category = primary_category(file.category_scores)
        drafts.append(
            SemanticChangeDraft(
                id=f"S{index}",
                title=file.path,
                files=[file.path],
                hunk_ids=hunk_ids,
                domains=[category.value],
                risk="low",
                confidence=1.0,
                unexpectedness=0.0,
            )
        )
    return drafts


def _signals_for(draft: SemanticChangeDraft, signals: list[StaticSignals]) -> list[StaticSignals]:
    wanted = set(draft.hunk_ids)
    files = set(draft.files)
    matched = [
        item
        for item in signals
        if (item.hunk_id and item.hunk_id in wanted) or item.file_path in files
    ]
    return matched or signals[:1]


def finalize(
    result: AnalysisResult,
    drafts: list[SemanticChangeDraft],
    config: HarpyConfig,
) -> list[LogicalChange]:
    changes = [
        score_change(draft, _signals_for(draft, result.signals), config.scoring) for draft in drafts
    ]
    changes.sort(key=lambda item: item.review_priority, reverse=True)
    return changes


def analyze_static(
    ref: str,
    *,
    config: HarpyConfig,
    repo: str | None = None,
    cwd: Path | None = None,
    use_ai: bool = True,
    use_cache: bool = True,
    provider: GhProvider | None = None,
    worktree_root: Path | None = None,
    progress: ProgressCallback | None = None,
) -> AnalysisResult:
    repo_arg, number = resolve_pr_ref(ref)
    repo_name = repo or repo_arg
    gh = provider or GhProvider(cwd=cwd)
    _note(progress, "Fetching pull request…")
    pr: PullRequest = gh.get_pr(number, repo=repo_name)
    key = cache_key(
        repo=pr.repo or repo_name or "local",
        base_sha=pr.base_sha or pr.base_ref,
        head_sha=pr.head_sha,
        model=config.semantic.model,
    )
    store = CacheStore(config.cache_dir)
    if use_cache:
        cached = store.get(key)
        if cached is not None and not cached.pending_semantic:
            _note(progress, "Loaded cached analysis.")
            return cached
    _note(progress, f"Fetching diff for {pr.repo or repo_name}#{pr.number}…")
    raw_diff = gh.get_diff(number, repo=repo_name or pr.repo or None)
    files = parse_unified_diff(raw_diff)
    if not files:
        files = list(pr.files)
    for file in files:
        apply_classification(file, extra_generated=config.generated_globs)

    manager = WorktreeManager(config.cache_dir)
    worktree: Path | None = None
    worktree_error: str | None = None
    source = worktree_root or cwd
    if pr.head_sha:
        _note(progress, "Preparing checkout…")
        try:
            worktree = manager.ensure(pr.repo or repo_name or "local", pr.head_sha, source=source)
        except (OSError, RuntimeError) as exc:
            worktree = None
            worktree_error = str(exc)

    hunks = [hunk for file in files for hunk in file.hunks]
    file_facts: list[FileFacts] = []
    if worktree:
        by_path: dict[str, FileFacts] = {}
        for file in files:
            source_text = read_source(worktree, file.path)
            facts = extract_file_facts(source_text, path=file.path)
            by_path[file.path] = facts
            if facts.has_any():
                file_facts.append(facts)
        for hunk in hunks:
            hunk_facts = by_path.get(hunk.file_path)
            if hunk_facts is not None and hunk_facts.symbols:
                hunk.changed_symbols = symbols_from_facts(hunk_facts, hunk)
            else:
                source_text = read_source(worktree, hunk.file_path)
                hunk.changed_symbols = symbols_for_hunk(hunk, source_text)

    _note(progress, f"Scoring {len(files)} files, {len(hunks)} hunks…")
    signals: list[StaticSignals] = []
    for file in files:
        signals.extend(extract_signals(file, config.scoring))

    symbols = [name for hunk in hunks for name in hunk.changed_symbols]
    refs = find_references(symbols, root=worktree or cwd or Path.cwd()) if symbols else []
    if refs and file_facts:
        refs = filter_hits(refs, file_facts)
    hunk_symbols = {hunk.id: hunk.changed_symbols for hunk in hunks}
    for signal in signals:
        names = hunk_symbols.get(signal.hunk_id or "", [])
        related = [hit for hit in refs if hit.symbol in names]
        if len(related) >= 3:
            signal.widely_referenced = True
            signal.raw_score = score_signals(signal, config.scoring)

    pending = bool(use_ai and config.semantic.enabled)
    workspace = worktree
    if workspace is None and pending:
        workspace = config.cache_dir / "scratch" / key.replace("/", "_")
        workspace.mkdir(parents=True, exist_ok=True)

    result = AnalysisResult(
        pr=pr,
        files=files,
        hunks=hunks,
        signals=signals,
        references=refs,
        file_facts=file_facts,
        semantic_available=False,
        workspace_path=str(workspace) if workspace else None,
        analysis_key=key,
        worktree_error=worktree_error,
        pending_semantic=pending,
    )
    result.changes = finalize(result, _static_drafts(result), config)
    result.api_impacts = extract_static_api_impacts(result)
    result.db_impacts = extract_static_db_impacts(result)
    enrich_contract_impacts(result)
    attach_blast_trees(result)
    if use_ai and not config.semantic.enabled:
        result.banner = DEGRADED_BANNER
    if use_cache and not pending and (result.semantic_available or not use_ai):
        store.put(key, result)
    _note(progress, "Static ranking ready.")
    return result


def _workspace_for(result: AnalysisResult, config: HarpyConfig) -> Path:
    workspace = (
        Path(result.workspace_path)
        if result.workspace_path
        else config.cache_dir / "scratch" / (result.analysis_key.replace("/", "_") or "scratch")
    )
    workspace.mkdir(parents=True, exist_ok=True)
    result.workspace_path = str(workspace)
    return workspace


def _run_semantic_call(
    result: AnalysisResult,
    *,
    config: HarpyConfig,
    workspace: Path,
    call: ScopeCall,
    known_changes: list[SemanticChangeDraft],
    semantic_client: SemanticAnalyzer | None,
) -> SemanticAnalysisResult:
    bundle = bundle_from_result(
        result,
        scope_ids=call.scope_ids,
        known_changes=known_changes,
        context_name=call.context_name,
    )
    if semantic_client is not None:
        return semantic_client.analyze_text(bundle, workspace=workspace)
    client = CursorAgentClient(with_model(config, call.model), context_name=call.context_name)
    return client.analyze_text(bundle, workspace=workspace)


def _finish_semantic(
    result: AnalysisResult,
    semantic: SemanticAnalysisResult,
    *,
    config: HarpyConfig,
    use_cache: bool,
) -> AnalysisResult:
    drafts = _static_drafts(result)
    banner: str | None = None
    if semantic.degraded:
        extra = semantic.error or result.worktree_error
        banner = f"{DEGRADED_BANNER} ({extra})" if extra else DEGRADED_BANNER
    else:
        result.pr_intent = semantic.pr_intent
        if semantic.changes:
            drafts = semantic.changes
            result.semantic_available = True
        else:
            banner = DEGRADED_BANNER
        if semantic.error:
            banner = f"Partial semantic analysis. {semantic.error}"
    result.changes = finalize(result, drafts, config)
    if semantic.api_impacts:
        result.api_impacts = semantic.api_impacts
    elif not result.api_impacts:
        result.api_impacts = extract_static_api_impacts(result)
    if semantic.db_impacts:
        result.db_impacts = semantic.db_impacts
    elif not result.db_impacts:
        result.db_impacts = extract_static_db_impacts(result)
    enrich_contract_impacts(result)
    attach_blast_trees(result)
    result.banner = banner
    result.pending_semantic = False
    if use_cache and result.analysis_key:
        try:
            CacheStore(config.cache_dir).put(result.analysis_key, result)
        except (OSError, TypeError, ValueError):
            pass
    return result


def apply_semantic(
    result: AnalysisResult,
    *,
    config: HarpyConfig,
    semantic_client: SemanticAnalyzer | None = None,
    use_cache: bool = True,
    plan: list[ScopeCall] | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
    scope_signature: str = "",
) -> AnalysisResult:
    result = result.model_copy(deep=True)
    if force:
        result.pending_semantic = True
        result.semantic_available = False
    if not result.pending_semantic:
        return result
    workspace = _workspace_for(result, config)
    write_symbol_facts(result, workspace)
    if scope_signature:
        result.scope_signature = scope_signature
        result.analysis_key = cache_key(
            repo=result.pr.repo or "local",
            base_sha=result.pr.base_sha or result.pr.base_ref,
            head_sha=result.pr.head_sha,
            model=config.semantic.model,
            scope_signature=scope_signature,
        )
    if plan is None:
        client = semantic_client or CursorAgentClient(config)
        _note(progress, "Asking cursor-agent (this can take several minutes)…")
        semantic = client.analyze_text(bundle_from_result(result), workspace=workspace)
        return _finish_semantic(result, semantic, config=config, use_cache=use_cache)
    if not plan:
        result.pending_semantic = False
        return result
    result.scopes_run = [scope_id for call in plan for scope_id in call.scope_ids]
    result.scope_signature = scope_signature
    stage0 = [call for call in plan if call.stage == 0]
    stage1 = [call for call in plan if call.stage == 1]
    pairs: list[tuple[ScopeCall, SemanticAnalysisResult]] = []
    known: list[SemanticChangeDraft] = []

    def run_call(
        call: ScopeCall, known_changes: list[SemanticChangeDraft]
    ) -> SemanticAnalysisResult:
        _note(progress, f"Analyzing {','.join(call.scope_ids)} · {call.model}")
        return _run_semantic_call(
            result,
            config=config,
            workspace=workspace,
            call=call,
            known_changes=known_changes,
            semantic_client=semantic_client,
        )

    for call in stage0:
        semantic = run_call(call, [])
        pairs.append((call, semantic))
        if semantic.changes:
            known = list(semantic.changes)
    if not known:
        known = _static_drafts(result)
    if len(stage1) == 1:
        call = stage1[0]
        pairs.append((call, run_call(call, known)))
    elif stage1:
        with ThreadPoolExecutor(max_workers=len(stage1)) as pool:
            futures = {pool.submit(run_call, call, known): call for call in stage1}
            for future in as_completed(futures):
                pairs.append((futures[future], future.result()))
    return _finish_semantic(result, merge_semantic(pairs), config=config, use_cache=use_cache)


def analyze(
    ref: str,
    *,
    config: HarpyConfig,
    repo: str | None = None,
    cwd: Path | None = None,
    use_ai: bool = True,
    use_cache: bool = True,
    provider: GhProvider | None = None,
    worktree_root: Path | None = None,
    semantic_client: SemanticAnalyzer | None = None,
    progress: ProgressCallback | None = None,
) -> AnalysisResult:
    result = analyze_static(
        ref,
        config=config,
        repo=repo,
        cwd=cwd,
        use_ai=use_ai,
        use_cache=use_cache,
        provider=provider,
        worktree_root=worktree_root,
        progress=progress,
    )
    if result.pending_semantic:
        _note(progress, "Asking cursor-agent (this can take several minutes)…")
        result = apply_semantic(
            result,
            config=config,
            semantic_client=semantic_client,
            use_cache=use_cache,
        )
    return result


def open_browser_selection(
    selection: OpenReview | OpenInbox,
    *,
    config: HarpyConfig,
    root: Path | None = None,
    progress: ProgressCallback | None = None,
) -> OpenReview:
    if isinstance(selection, OpenReview):
        return selection
    result = analyze_static(
        str(selection.number),
        config=config,
        repo=selection.repo,
        progress=progress,
    )
    item = persist_analysis(result, root=root)
    if item.review_id is None:
        raise RuntimeError("analysis persist did not assign a review id")
    return OpenReview(result=result, review_id=item.review_id)


def persist_analysis(result: AnalysisResult, *, root: Path | None = None) -> BrowserItem:
    from harpy.analysis.workflows.browser import persist_analysis as persist

    return persist(result, root=root)


def list_browser(
    tab: str = "local",
    *,
    offline: bool = False,
    root: Path | None = None,
    refresh_remote: bool = False,
) -> list[BrowserItem]:
    from harpy.analysis.workflows.browser import list_browser as listing

    return listing(tab, offline=offline, root=root, refresh_remote=refresh_remote)


def load_analysis(review_id: object, *, root: Path | None = None) -> AnalysisResult | None:
    from uuid import UUID

    from harpy.analysis.workflows.browser import load_analysis as load

    ident = review_id if isinstance(review_id, UUID) else UUID(str(review_id))
    return load(ident, root=root)


def save_review_session(session: ReviewSession, *, root: Path | None = None) -> None:
    from harpy.analysis.workflows.session import save_review_session as persist

    persist(session, root=root)


def load_review_session(review_id: object, *, root: Path | None = None) -> ReviewSession | None:
    from uuid import UUID

    from harpy.analysis.workflows.session import load_review_session as load

    ident = review_id if isinstance(review_id, UUID) else UUID(str(review_id))
    return load(ident, root=root)


def __getattr__(name: str) -> object:
    if name == "ReviewService":
        from harpy.analysis.service import ReviewService

        return ReviewService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
