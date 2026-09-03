# ADR 0001 — Semantic analysis is read-only cursor-agent

## Status

Accepted

## Context

impl.md specified `codex exec --output-schema`. The available tool is `cursor-agent` 2026.08.31, which has no `--output-schema` and can write/execute when not constrained.

The analyzer reads a stranger's PR head. Write or shell access is unacceptable.

## Decision

- Invoke `cursor-agent -p --output-format json --mode ask --trust --workspace <pr-worktree>`.
- `--mode ask` is read-only.
- Workspace is a `git worktree` of the head SHA so untracked/ignored files (`.env`, secrets) are not present.
- Structured output is prompt-enforced and validated locally (see ADR 0002).
- Default model is `cursor-grok-4.6-high-fast`.

## Consequences

- No schema flag; parser must be tolerant and degrade.
- Builder agents (`--force`) are a separate role and must not share this invocation.
