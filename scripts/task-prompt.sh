#!/usr/bin/env bash
set -euo pipefail
task="${1:?task file}"
cat <<EOF
Read AGENTS.md and ${task}.
Implement that single task.
Run make check and leave it green.
Do not edit or delete existing tests to make the change pass.
Do not call cursor-agent from tests unless marked @pytest.mark.cursor.
Do not touch other docs/tasks files except this task's status field.
Do not add a git remote.
Then stop.
EOF
