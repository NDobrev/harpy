# Harpy — Agent instructions

Harpy is a terminal PR reviewer. The product unit is a **logical change**, not a file. Guiding principle: compress code volume, not decision information.

Design: [docs/design/impl.md](docs/design/impl.md). Glossary: [docs/CONTEXT.md](docs/CONTEXT.md). Backlog: [docs/tasks/](docs/tasks/).

## Layering

```text
cli.py → analysis/pipeline.py
              ├─ github/          (gh CLI via proc.py)
              ├─ git/             (worktree + diff via proc.py)
              ├─ analysis/        (classifier, signals, symbols, references)
              ├─ semantic/        (cursor-agent, read-only)
              ├─ analysis/scoring.py  (imports models.py only)
              └─ cache/
tui/ → pipeline.py only
```

Hard invariants:

- `tui/` never imports `semantic/`.
- `semantic/` never imports `tui/`.
- `scoring.py` imports only `harpy.models` (and stdlib / pydantic).
- Nothing outside `src/harpy/proc.py` imports `subprocess`.
- The TUI never calls `cursor-agent`. Scoring never renders UI.

`tests/test_architecture.py` enforces this. A layer violation fails `make check`.

## Agent roles and model

Pinned model for every role: `cursor-grok-4.6-high-fast`.

| Role | Permission | Invocation |
|---|---|---|
| Author | write + shell (this chat / Task) | `model: cursor-grok-4.6-high-fast` |
| Builder | write + shell, isolated worktree | `scripts/build-task.sh HP-xxx` → `--force --worktree` |
| Analyzer | read-only | `cursor-agent -p --mode ask --trust --model cursor-grok-4.6-high-fast` |

The analyzer that reads a stranger's PR head must not write or execute. Do not collapse these roles.

The model constant must agree in `HARPY_AGENT_MODEL` (`scripts/build-task.sh`), `[semantic] model` in `.harpy.toml`, and `DEFAULT_MODEL` in `src/harpy/config.py`. A test asserts this.

## Verification

`make check` is the only acceptance command (`fmt`, `lint`, `types`, `test`). Every task is done when `make check` is green.

## Working rules

- Never edit or delete an existing test to make a change pass. Add a test, or stop and ask.
- Never call `cursor-agent` from a test unless the test is marked `@pytest.mark.cursor`.
- Do not require network or a live agent for `make check`.
- Update `docs/tasks/HP-xxx.md` `status:` when you start (`doing`) and finish (`done`).
- Add an ADR under `docs/adr/` when a decision changes.
- Do not touch other task files than the one you were asked to implement.
- Do not add a git remote. This repo is local-only (see `docs/adr/0003-local-only-repo.md`).

## How to pick work

```bash
make tasks          # ready queue: status=todo, dependencies done
make build-task ID=HP-007
```

Then land with the `land-task` skill (`git merge --no-ff` into local `main`).
