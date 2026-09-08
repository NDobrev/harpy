# ADR 0014 — Unified TUI navigation

## Status

Accepted

## Context

The TUI is a fixed three-pane viewer: change list, focused diff, context.
That layout does not fit a review workspace with lenses, freshness, a
command palette, or a decision inspector. Narrow terminals become unusable if
three panes are mandatory.

## Decision

- Replace the fixed three-pane requirement with a responsive workspace:
  navigator, evidence/content canvas, and decision/context inspector.
- Width ≥140 columns keeps three regions. 100–139 columns opens the inspector
  as a drawer. Below 100 columns, one pane is active with explicit tabs.
- Semantic analysis still does not start until `s` confirms a scope.
- Existing shortcuts remain aliases where practical (`e`, `i`, `r`, `t`, `o`,
  `s`, `/`, `q`).
- The TUI reaches storage, source files, semantic analysis, GitHub, and
  verification only through the facade/service.

## Consequences

- `src/harpy/tui/AGENTS.md` no longer requires three simultaneous panes.
- Provider events must not steal focus or replace another review's screen.
- The workspace implementation is HP-054; this ADR fixes the navigation
  contract first.
