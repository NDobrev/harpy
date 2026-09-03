# ADR 0005 — Database impact lives in the same contract view

## Status

Accepted

## Context

Schema and migration changes need the same review surface as endpoint contracts:
what changed, who is affected, whether it is breaking, and a diagram only when
prose would hide the data model or migrate/backfill flow.

## Decision

- `AnalysisResult.db_impacts` is listed in the existing `i` impact view next to `api_impacts`.
- The read-only analyzer may emit `db_impacts` for schema, migration, or persistence-contract changes.
- Routine query tweaks are not `db_impacts`.
- Diagrams stay optional. Static extraction may list table/column operations; it never invents diagrams.

## Consequences

- Prompt version is part of the cache key (see ADR 0006 for the current version).
- The TUI stays usable when both lists are empty.
- Schema boxes are the diagram for DB items (ADR 0006).
