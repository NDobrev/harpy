# ADR 0009 — Review scope dialog and per-scope models

## Status

Accepted

## Context

Semantic analysis was a single automatic `cursor-agent` call on TUI open. Reviewers
could not choose what to spend agent time on, or which model to use for which
concern. Security, tests, questions, and omissions were fields inside one
monolithic JSON object, not selectable work.

## Decision

- The TUI does not start semantic analysis on mount. `s` opens a modal.
- Eight scopes, derived from the current prompt: `changes`, `api`, `db`,
  `security`, `questions`, `tests`, `omissions`, `diagrams`.
- `diagrams` is a modifier: no model of its own; it rides with `api`/`db` and
  is forced off when both contracts are off.
- Default: every scope on, every call-scope model is `cursor-grok-4.6-high-fast`.
- Last choice lives in `~/.config/harpy/scope.json`. Named presets live in
  `presets.json`. Built-ins cannot be deleted.
- Scopes that share a model collapse into one `cursor-agent` call. The all-grok
  default is still one call. The call that contains `changes` runs first so
  later calls can reference real change ids.
- A failed call degrades only its own scopes. The banner names them.
- Disabling `security` leaves `security_sensitivity` and `data_sensitivity` at
  0, which lowers `importance`. That is inherent to scoping.

## Consequences

- `PROMPT_VERSION` is 10. Cache keys stay stable for the default full-scope
  plan (`scope_signature=""`). Narrower plans get their own key.
- The TUI imports `harpy.review_scope` and `harpy.prefs`. It still never
  imports `harpy.semantic`.
