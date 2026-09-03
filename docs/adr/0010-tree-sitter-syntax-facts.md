# ADR 0010 — Tree-sitter syntax facts

## Status

Accepted

## Context

Symbol extraction was Python `ast` plus ripgrep on the last name segment. TypeScript,
Go, Rust, and SQL hunks produced empty `changed_symbols`, so reference search never
ran and the analyzer bundle had no structured syntax context. LSP was rejected for
this path: it needs a long-lived process, and several servers execute project code
on a stranger's PR head (ADR 0001).

## Decision

- Add `tree-sitter` and one pinned grammar package per supported language as hard
  runtime dependencies: Python, TypeScript/TSX, Go, Rust, SQL.
- Extract `DEF`, `IMP`, `ROUTE`, and `DDL` facts from the PR-head worktree. Syntax
  only. No types, no cross-file resolution, no diagnostics.
- Deliver facts as `SYMBOL_FACTS.md` in the worktree. The prompt points at it;
  the analyzer greps by path. The inline `REFERENCES` block is filtered by the
  import graph and trimmed.
- A grammar version bump requires an `ANALYSIS_VERSION` bump so cached analyses
  do not mix parsers.
- ORM-defined schemas (Alembic, Drizzle, Ent, Diesel, Prisma) stay on the host
  language or the existing regex fallback. They are not the SQL grammar.
- `docs/design/impl.md` remains the canonical design doc. The repo-root `impl.md`
  is a duplicate; do not treat it as a second source of truth.

## Consequences

- Runtime dependencies grow from four to ten.
- `ANALYSIS_VERSION` is 2. `PROMPT_VERSION` is 11.
- `analysis/syntax/` must not import `harpy.tui` or `harpy.semantic`.
- Missing or failed grammars degrade to the previous AST/regex behavior.
