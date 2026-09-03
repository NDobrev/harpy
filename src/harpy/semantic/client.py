"""Read-only cursor-agent client."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from harpy.config import DEFAULT_MODEL, HarpyConfig
from harpy.models import SemanticAnalysisResult
from harpy.proc import run
from harpy.semantic.parser import parse_agent_stdout, parse_semantic
from harpy.semantic.prompts import CONTEXT_FILENAME, repair_prompt, short_prompt

DEGRADED_BANNER = "Semantic analysis unavailable. Showing static review priority only."


class CursorAgentClient:
    def __init__(self, config: HarpyConfig, *, context_name: str = CONTEXT_FILENAME) -> None:
        self.config = config
        self.context_name = context_name

    def analyze_text(self, prompt: str, *, workspace: Path) -> SemanticAnalysisResult:
        if not self.config.semantic.enabled:
            return SemanticAnalysisResult(degraded=True, error="semantic disabled")
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / self.context_name).write_text(prompt, encoding="utf-8")
        raw, error = self._raw(short_prompt(self.context_name), workspace=workspace)
        if error:
            return SemanticAnalysisResult(degraded=True, error=error)
        try:
            return parse_semantic(raw)
        except (ValidationError, ValueError, TypeError) as exc:
            repaired, repair_error = self._raw(
                repair_prompt(str(exc), context_name=self.context_name), workspace=workspace
            )
            if repair_error:
                return SemanticAnalysisResult(degraded=True, error=str(exc))
            try:
                return parse_semantic(repaired)
            except (ValidationError, ValueError, TypeError) as retry_exc:
                return SemanticAnalysisResult(degraded=True, error=str(retry_exc))

    def _raw(self, prompt: str, *, workspace: Path) -> tuple[str, str | None]:
        argv = [
            "cursor-agent",
            "-p",
            "--output-format",
            "json",
            "--mode",
            "ask",
            "--trust",
            "--model",
            self.config.semantic.model or DEFAULT_MODEL,
            "--workspace",
            str(workspace),
            "--",
            prompt,
        ]
        result = run(argv, timeout=self.config.semantic.timeout_seconds, cwd=workspace)
        if not result.ok:
            return "", result.stderr.strip() or f"cursor-agent exited {result.returncode}"
        text, _session = parse_agent_stdout(result.stdout)
        return text, None
