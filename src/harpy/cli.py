"""Typer CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from harpy.config import CONFIG_NAME, HarpyConfig, default_toml_text, load_config
from harpy.git.repository import is_git_repo
from harpy.git.worktree import WorktreeManager
from harpy.proc import run, which
from harpy.semantic.schemas import semantic_json_schema

app = typer.Typer(no_args_is_help=True, add_completion=False)
cache_app = typer.Typer(help="Cache operations")
config_app = typer.Typer(help="Configuration")
app.add_typer(cache_app, name="cache")
app.add_typer(config_app, name="config")
_COMMANDS = frozenset({"analyze", "doctor", "schema", "cache", "config", "review"})
_VALUE_OPTS = frozenset({"--repo", "--model"})


def rewrite_argv(args: list[str]) -> list[str]:
    """Insert `review` for `harpy 1842` and `harpy --repo owner/name 1842`."""
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
) -> None:
    config = _config(model)
    from harpy.tui.app import run_tui

    if debug:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    def progress(message: str) -> None:
        typer.echo(message, err=True)

    try:
        from harpy.analysis.pipeline import analyze_static

        result = analyze_static(
            pr,
            config=config,
            repo=repo,
            use_ai=not no_ai,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    if result.pending_semantic:
        progress("Opening review. Press s to choose review scope…")
    run_tui(result, config=config)


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
    if as_json:
        typer.echo(result.model_dump_json(indent=2))
        return
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
def schema() -> None:
    typer.echo(json.dumps(semantic_json_schema(), indent=2))


@cache_app.command("clean")
def cache_clean() -> None:
    from harpy.cache.store import CacheStore

    store = CacheStore()
    analyses = store.clear()
    removed = WorktreeManager().cleanup(now=10**12)
    typer.echo(f"removed {analyses} analyses, {len(removed)} worktrees")


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
