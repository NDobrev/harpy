# ADR 0011 — Snapshot-based reviews

## Status

Accepted

## Context

`AnalysisResult` mixes live worktree paths, PR metadata, and presentation state.
Opening a review after the worktree expired, or after the PR head moved, could
show a new diff under an old explanation. Evidence resolved through a live
worktree path is not reproducible.

## Decision

- Every review is bound to an immutable `RevisionSnapshot`: base-tip SHA,
  comparison-base SHA, head SHA or local content digest, file manifest, and
  diff digest.
- Source reads use captured blobs or captured local content. They do not follow
  an arbitrary live worktree path or snapshot symlink onto the host.
- New serialized reports use `schema_version=2`. Sequential `H1`/`C1` ids remain
  valid inside one analysis response; durable identity is a UUID.
- Existing V1 `AnalysisResult` constructors stay supported.

## Consequences

- Historical reports remain readable after worktree cleanup.
- A moved PR head updates freshness; it does not replace the selected report.
- Later acquisition work (HP-044) must record merge base separately from
  base-tip SHA.
