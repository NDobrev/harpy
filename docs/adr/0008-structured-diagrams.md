# ADR 0008 — Structured diagrams on the impact pane

## Status

Accepted

## Context

Mermaid source and a flat arrow list are not enough to review a contract. Reviewers
need sequence lifelines, flow boxes, ER connectors, and an approximate blast tree,
and they need to jump from a node into the matching file.

## Decision

- `ApiDiagram` and each API/DB impact may carry structured `sequence`, `flow`, and `tree`.
- Mermaid remains a fallback that is parsed into that IR. The TUI never treats mermaid as the picture.
- ASCII renderers live in `harpy.analysis.diagrams` and return `RenderedDiagram` lines plus hitboxes.
- The impact diagram pane cycles pictures (`[` / `]`), highlights hits (`j` / `k`), and `enter` opens a file.
- Sequence and flow stay optional (ADR 0004). A blast tree is filled from `ReferenceHit` when omitted.
- Blast radius stays an approximation. Static extraction still does not invent sequence or flow.

## Consequences

- Prompt version is part of the cache key (`PROMPT_VERSION=9`).
- `visualize_diagrams` keeps its old “schema wins” string contract for existing tests.
- New callers use `render_pictures`, which emits every picture.
