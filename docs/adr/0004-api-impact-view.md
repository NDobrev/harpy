# ADR 0004 — API impact view, diagrams only when they clarify

## Status

Accepted

## Context

Endpoint and route contract changes need a review surface separate from hunks.
A sequence or before/after diagram helps only when the prose would hide the flow.

## Decision

- `AnalysisResult.api_impacts` is the source for a dedicated TUI view (`i`).
- The read-only analyzer may emit `api_impacts` and optional mermaid `diagrams`.
- Diagrams are omitted unless they clarify a contract the reviewer would otherwise miss.
- Static extraction may list method/path pairs when the agent has not run; it never invents diagrams.

## Consequences

- Prompt version is part of the cache key (see ADR 0005 for the current version).
- The TUI must stay usable when `api_impacts` is empty.
- Database contract changes share this view (`db_impacts`, ADR 0005).
