---
name: land-task
description: Merge an HP-xxx builder worktree into local main with --no-ff. No GitHub PR (repo is local-only).
---

# Land a task

The repo has no remote. Do not run `gh pr create`.

1. Identify the worktree: `~/.cursor/worktrees/harpy-pr/<HP-id>` (or `git worktree list`).
2. In the worktree: `make check`.
3. On local `main`:

```bash
git merge --no-ff hp-<id> -m "HP-xxx: <title>"
```

Use `--no-ff` so each ticket is one reviewable merge commit.

4. Set `status: done` in `docs/tasks/HP-xxx.md` if the builder did not.
5. `git worktree remove` the builder worktree.
6. `make check` on `main`.
