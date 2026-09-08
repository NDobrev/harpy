"""Typer CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from harpy.config import CONFIG_NAME, HarpyConfig, default_toml_text, load_config
from harpy.git.repository import is_git_repo
from harpy.git.worktree import WorktreeManager
from harpy.proc import run, which
from harpy.semantic.schemas import semantic_json_schema

app = typer.Typer(no_args_is_help=False, add_completion=False)
cache_app = typer.Typer(help="Cache operations")
config_app = typer.Typer(help="Configuration")
app.add_typer(cache_app, name="cache")
app.add_typer(config_app, name="config")
_COMMANDS = frozenset(
    {"analyze", "doctor", "schema", "cache", "config", "review", "browse", "history"}
)
_VALUE_OPTS = frozenset({"--repo", "--model"})


def rewrite_argv(args: list[str]) -> list[str]:
    """Insert `review` for `harpy 1842` and `harpy --repo owner/name 1842`."""
    if not args:
        return ["browse"]
    index = 0
    while index < len(args):
        token = args[index]
        if token in {"-h", "--help"}:
            return args
        if token in _COMMANDS:
            return args
        if token in _VALUE_OPTS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return ["review", *args]
    return args


def _config(model: str | None, start: Path | None = None) -> HarpyConfig:
    return load_config(cli_model=model, start=start)


def _doctor_payload(config: HarpyConfig, cwd: Path) -> dict[str, object]:
    checks: dict[str, bool] = {
        "git": which("git") is not None,
        "gh": which("gh") is not None,
        "cursor_agent": which("cursor-agent") is not None,
        "rg": which("rg") is not None,
        "repository": is_git_repo(cwd),
    }
    gh_auth = False
    if checks["gh"]:
        result = run(["gh", "auth", "status"], timeout=10)
        gh_auth = result.ok
    checks["gh_auth"] = gh_auth
    return {
        "checks": checks,
        "model": config.semantic.model,
        "model_source": config.semantic.model_source,
        "semantic_enabled": config.semantic.enabled,
        "config_path": str(config.path) if config.path else None,
    }


@app.command()
def review(
    pr: Annotated[str, typer.Argument(help="PR number, URL, or .")],
    repo: Annotated[str | None, typer.Option("--repo")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    no_ai: Annotated[bool, typer.Option("--no-ai")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    report: Annotated[str | None, typer.Option("--report")] = None,
) -> None:
    config = _config(model)
    from harpy.tui.app import run_tui

    if debug:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    def progress(message: str) -> None:
        typer.echo(message, err=True)

    if report:
        from harpy.analysis.workflows.browser import load_open_review_by_report

        try:
            opened = load_open_review_by_report(UUID(report))
        except ValueError as exc:
            typer.secho("invalid report id", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        if opened is None:
            typer.secho("report not found", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        run_tui(opened.result, config=config, review_id=opened.review_id)
        return

    try:
        from harpy.analysis.pipeline import analyze_static, persist_analysis

        result = analyze_static(
            pr,
            config=config,
            repo=repo,
            use_ai=not no_ai,
            progress=progress,
        )
        item = persist_analysis(result)
    except Exception as exc:  # noqa: BLE001
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    if result.pending_semantic:
        progress("Opening review. Press s to choose review scope…")
    run_tui(result, config=config, review_id=item.review_id)


def main() -> None:
    import sys

    sys.argv = [sys.argv[0], *rewrite_argv(sys.argv[1:])]
    app()


@app.command()
def analyze(
    pr: Annotated[str, typer.Argument()],
    repo: Annotated[str | None, typer.Option("--repo")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    static: Annotated[bool, typer.Option("--static")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
    no_ai: Annotated[bool, typer.Option("--no-ai")] = False,
    cache_only: Annotated[bool, typer.Option("--cache-only")] = False,
    incremental: Annotated[bool, typer.Option("--incremental")] = False,
    full: Annotated[bool, typer.Option("--full")] = False,
    preset: Annotated[str | None, typer.Option("--preset")] = None,
    intent_file: Annotated[Path | None, typer.Option("--intent-file")] = None,
    schema_version: Annotated[int | None, typer.Option("--schema-version")] = None,
) -> None:
    config = _config(model)
    from harpy.analysis.pipeline import analyze as run_analyze

    def progress(message: str) -> None:
        typer.echo(message, err=True)

    result = run_analyze(
        pr,
        config=config,
        repo=repo,
        use_ai=not (no_ai or static),
        progress=progress,
    )
    from harpy.analysis.pipeline import persist_analysis

    persist_analysis(result)
    if static:
        ranked = sorted(
            result.files,
            key=lambda item: max((h.static_score for h in item.hunks), default=0),
            reverse=True,
        )
        for file in ranked:
            score = max((hunk.static_score for hunk in file.hunks), default=0)
            typer.echo(f"{score:5.0f} {file.path}")
        return
    if cache_only:
        typer.echo(f"cached {result.analysis_key} semantic={result.semantic_available}")
        return
    if as_json:
        if schema_version == 2:
            typer.echo(json.dumps({"schema_version": 2, "analysis_key": result.analysis_key}))
            return
        typer.echo(result.model_dump_json(indent=2))
        return
    _ = (incremental, full, preset, intent_file)
    for change in result.changes:
        typer.echo(f"{change.review_priority:5.0f} {change.risk:8} {change.title}")


@app.command()
def doctor(
    model: Annotated[str | None, typer.Option("--model")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    config = _config(model)
    payload = _doctor_payload(config, Path.cwd())
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    checks = payload["checks"]
    assert isinstance(checks, dict)
    for name, ok in checks.items():
        mark = "✓" if ok else "✗"
        typer.echo(f"{mark} {name}")
    typer.echo(f"model: {payload['model']} ({payload['model_source']})")


@app.command()
def browse(offline: Annotated[bool, typer.Option("--offline")] = False) -> None:
    config = _config(None)
    from harpy.analysis.pipeline import open_browser_selection
    from harpy.tui.app import run_tui
    from harpy.tui.screens.browser import run_browser

    def progress(message: str) -> None:
        typer.echo(message, err=True)

    while True:
        picked = run_browser(offline=offline)
        if picked is None:
            return
        try:
            opened = open_browser_selection(picked, config=config, progress=progress)
        except Exception as exc:  # noqa: BLE001
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            continue
        if opened.result.pending_semantic:
            progress("Opening review. Press s to choose review scope…")
        run_tui(opened.result, config=config, review_id=opened.review_id)


@app.command()
def history(review_reference: str) -> None:
    from harpy.analysis.workflows.browser import history_for

    items = history_for(review_reference)
    if not items:
        typer.echo("no local reports")
        raise typer.Exit(2)
    for item in items:
        typer.echo(
            f"{item.report_id}  {item.repo}#{item.number}  {item.title}  "
            f"{item.analyzed_rev}  {item.freshness.value}  {item.completeness}"
        )


@app.command()
def schema(
    version: Annotated[int | None, typer.Option("--version")] = None,
) -> None:
    if version == 2:
        from harpy.models import AnalysisReport

        typer.echo(json.dumps(AnalysisReport.model_json_schema(), indent=2))
        return
    typer.echo(json.dumps(semantic_json_schema(), indent=2))


@cache_app.command("stats")
def cache_stats() -> None:
    from harpy.cache.artifacts import ArtifactCache

    stats = ArtifactCache().stats()
    typer.echo(f"{stats['count']} artifacts, {stats['bytes']} bytes")


@cache_app.command("explain")
def cache_explain(report_or_run_id: str) -> None:
    from harpy.cache.artifacts import ArtifactCache

    meta = ArtifactCache().explain(report_or_run_id)
    if meta is None:
        typer.echo("unknown artifact")
        raise typer.Exit(2)
    typer.echo(f"{meta.key} kind={meta.kind} size={meta.size} invalidation={meta.invalidation}")


@cache_app.command("clean")
def cache_clean() -> None:
    from harpy.cache.artifacts import ArtifactCache
    from harpy.cache.store import CacheStore

    store = CacheStore()
    analyses = store.clear()
    artifacts = ArtifactCache().clean()
    removed = WorktreeManager().cleanup(now=10**12)
    typer.echo(f"removed {analyses} analyses, {artifacts} artifacts, {len(removed)} worktrees")


@config_app.command("init")
def config_init(
    model: Annotated[str | None, typer.Option("--model")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    path = Path.cwd() / CONFIG_NAME
    if path.exists() and not force:
        typer.echo(f"{path} already exists")
        raise typer.Exit(1)
    config = _config(model)
    path.write_text(default_toml_text(config), encoding="utf-8")
    typer.echo(f"wrote {path} model={config.semantic.model}")
