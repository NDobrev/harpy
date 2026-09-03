# ADR 0002 — No --output-schema; recover JSON locally

## Status

Accepted

## Context

`cursor-agent` 2026.08.31 has no `--output-schema`. Documented success envelope:

```json
{"type":"result","subtype":"success","is_error":false,"result":"<text>","session_id":"..."}
```

On failure the process exits non-zero and writes stderr; no well-formed JSON is guaranteed.

## Spike (2026-09-02, `cursor-grok-4.6-high-fast`)

Recorded under `tests/fixtures/cursor/`.

1. **Argv prompt** (`-- 'Reply with exactly this JSON...'`) in `--mode ask --trust` returned a success envelope whose `result` was exactly `{"ok":true}` — no wrapping prose. Exit 0.
2. **Stdin prompt** also worked (print mode inferred) and produced the same clean JSON. Either path is valid; the client uses argv after `--` so the prompt cannot be confused with workspace-trust UI.
3. **Invalid model** exited 1, empty stdout, stderr `Cannot use this model: ...`. Matches the documented failure shape.
4. Ask-mode JSON cleanliness for this pinned model is high enough that a last-fence / balanced-object extractor is sufficient.

## Decision

1. Invoke with `-p --output-format json --mode ask --trust --model <DEFAULT_MODEL> --workspace <worktree> -- <prompt>`.
2. Parse the `result` field, then take the last fenced `json` block or the first balanced `{...}`.
3. Validate with Pydantic. Retry once with the validation error. Else degrade to static-only.
4. Hard timeout on `proc.run` so a hung read-only tool request cannot freeze the TUI.

## Consequences

JSON cleanliness is model-specific — another reason the analyzer model is pinned. Tests replay fixtures; they do not call live `cursor-agent` unless marked `@pytest.mark.cursor`.
