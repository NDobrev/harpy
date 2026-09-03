#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 && -z "${ID:-}" ]]; then
  echo "usage: scripts/build-task.sh HP-xxx" >&2
  exit 2
fi
TASK_ID="${1:-$ID}"
TASK_ID="${TASK_ID#docs/tasks/}"
TASK_ID="${TASK_ID%.md}"

HARPY_AGENT_MODEL="${HARPY_AGENT_MODEL:-cursor-grok-4.6-high-fast}"
task="docs/tasks/${TASK_ID}.md"
if [[ ! -f "$task" ]]; then
  echo "missing $task" >&2
  exit 2
fi

mkdir -p "$ROOT/.harpy/builds"
log="$ROOT/.harpy/builds/${TASK_ID}.ndjson"

prompt="$("$ROOT/scripts/task-prompt.sh" "$task")"

# Isolated worktree + write/shell. Never run --force in the checked-out tree.
cursor-agent -p --force --trust \
  --model "$HARPY_AGENT_MODEL" \
  --worktree "$TASK_ID" --worktree-base main \
  --output-format stream-json \
  -- "$prompt" | tee "$log"
