#!/usr/bin/env bash
set -euo pipefail
# afterFileEdit: stdin is JSON with a "file" or "path" field.
path="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("path") or d.get("file") or "")')"
if [[ -z "${path}" || ! -f "${path}" ]]; then
  exit 0
fi
case "${path}" in
  *.py)
    if command -v uv >/dev/null 2>&1; then
      uv run ruff format -- "${path}" >/dev/null
      uv run ruff check --fix -- "${path}" >/dev/null || true
    fi
    ;;
esac
exit 0
