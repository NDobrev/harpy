# ADR 0012 — Durable review memory

## Status

Accepted

## Context

Analysis lives in a recomputable cache. Closing Harpy, cleaning worktrees, or
changing scoring dropped human decisions, notes, and the last selected report.
Daily review needs those records to survive.

## Decision

- Store durable state in standard-library SQLite plus content-addressed files
  under the existing XDG/home-directory conventions.
- Persist completed and partial reports, cited excerpts, review decisions,
  notes, drafts, and finding history.
- Treat raw provider responses, syntax facts, and retrieval intermediates as
  cache. `cache clean` must not delete reports or human review work.
- A corrupt durable database is an actionable error. Never replace it with an
  empty database.
- No cloud synchronization and no server database.

## Consequences

- Storage and TUI stay decoupled: the TUI reaches durable state only through
  the application facade.
- History deletion is an explicit operation, separate from cache cleanup.
- Schema migrations use a backup and refuse writes when the file is newer than
  the application supports (HP-045).
