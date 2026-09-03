#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [[ ! -f Makefile ]]; then
  exit 0
fi
make check
