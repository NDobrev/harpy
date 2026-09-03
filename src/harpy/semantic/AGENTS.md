# Semantic layer

Read-only `cursor-agent` integration. Never import `harpy.tui`. Never spawn `--force`.

- Invoke: `-p --output-format json --mode ask --trust --model <cfg.semantic.model> --workspace <pr-worktree>`.
- Default model is `cursor-grok-4.6-high-fast`. Per-scope override is allowed.
- Prompt must request one JSON object and no prose. There is no `--output-schema`.
- Validate with Pydantic. One repair retry with the validation error. Then degrade to static-only.
- Prompt version is part of the cache key. Bump `PROMPT_VERSION` when the prompt changes.
- Never send lockfiles, generated-file bodies, `.env`, or secrets.
