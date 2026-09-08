# ADR 0013 — Staged analysis and cache identity

## Status

Accepted

## Context

One cache key mixed static facts, semantic grouping, and scoring. A scoring
tweak or a custom scope plan could miss a valid semantic hit, or worse, treat
static output as a semantic result. Incremental updates need independently
keyed artifacts.

## Decision

- Key source, syntax, static analysis, semantic scope, and ranking artifacts
  separately.
- Scoring changes must not invalidate semantic artifacts.
- Titles, descriptions, task files, and repository invariants are semantic
  inputs and participate in invalidation.
- Queries, report open, and lens changes do not start semantic analysis.
- Preparing an analysis, submission, or verification does not execute it.
- Reused results keep their assessment status and add provenance. `cached` is
  not an assessment state.

## Consequences

- Custom-scope results are retrieved by actual scope identity.
- Legacy JSON analyses import as historical reports with legacy provenance;
  they are never V2 semantic cache hits.
- Incremental reuse and the V2 provider protocol land in later tasks
  (HP-046–HP-049).
