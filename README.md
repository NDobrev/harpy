# Harpy

Terminal pull-request reviewer for repositories with large amounts of AI-generated code.

> Compress code volume, not decision information.

Harpy groups a PR into **logical changes**, ranks them by review importance, and shows before/after behavior, risk, blast radius, and questions — then the exact focused diff.

```text
$ harpy 1842
```

## Requirements

- Python 3.12+
- `git`, `gh` (authenticated)
- `cursor-agent` (optional; static analysis works without it)
- `rg` optional; a Python fallback is used when ripgrep is missing

## Setup

```bash
make setup
make check
harpy doctor
```

## Commands

```bash
harpy 1842
harpy analyze 1842 --json
harpy analyze 1842 --static
harpy --repo owner/name 1842
harpy doctor --json
harpy schema
harpy cache clean
harpy config init
```

Agent-facing entry point is the Makefile. See [AGENTS.md](AGENTS.md).

Design source: [docs/design/impl.md](docs/design/impl.md).
