# ADR 0006 — Terminal schema visualizer

## Status

Accepted

## Context

Mermaid source in the impact diagram pane is hard to review. A schema change
needs tables, columns, and relations as boxes a reviewer can scan.

## Decision

- `DbChangeImpact.schema_snapshot` is structured tables/columns/relations with change marks (JSON key `schema`).
- When a snapshot has table/column/relation changes, the TUI draws OLD and NEW table boxes.
- Only relations that changed (`add` / `drop` / `alter`) are drawn. Unchanged FKs are omitted.
- Mermaid is a fallback when there is no structured snapshot.
- Static extraction fills a snapshot from DDL, including new FKs from `REFERENCES`.
- The impact layout widens the diagram pane (`1fr 1fr 2fr`).

## Consequences

- Prompt version is part of the cache key (`PROMPT_VERSION=6`).
- Box drawing uses nowrap so alignment survives.
