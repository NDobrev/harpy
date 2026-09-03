---
name: pick-up-task
description: Pick the next ready HP-xxx task and dispatch the isolated builder agent.
---

# Pick up a task

```bash
make tasks
make build-task ID=HP-xxx
```

`make tasks` prints `status: todo` items whose `depends_on` are all `done`.

Do not implement in the checked-out tree. `scripts/build-task.sh` starts `cursor-agent --force` in `~/.cursor/worktrees/harpy-pr/<id>` on model `cursor-grok-4.6-high-fast`.

After the builder finishes, use the `land-task` skill.
