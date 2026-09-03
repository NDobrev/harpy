# ADR 0003 — Local-only repository

## Status

Accepted

## Context

The workspace has no GitHub remote. Adding one was explicitly declined.

## Decision

- `git init -b main` only. No `git remote add`, no `gh repo create`.
- Backlog is `docs/tasks/HP-*.md`. `make tasks` is the ready queue.
- Land work with `git merge --no-ff` (skill `land-task`), not `gh pr create`.
- `.github/workflows/check.yml` is committed but dormant until a remote exists.
- The real gate is `make check` plus the `stop` hook.
- End-to-end acceptance uses external public PRs: `make review REPO=<owner/repo> PR=<n>`.

## When a remote is added later

1. `gh repo create` (or add origin) and push `main`.
2. GitHub Actions will run the existing workflow.
3. Keep `--no-ff` history; it is already PR-shaped.
4. Optional: mirror open `docs/tasks` to issues.
