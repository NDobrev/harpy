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

## Choose analysis checks

Press `s` in a review to configure analysis. Move through grouped checks with
arrows or `j`/`k`, toggle with Space or a mouse click, and press Enter in the
check list (or select **Start analysis**) to run. Selecting scopes never starts
analysis automatically. The footer shows planned AI calls; selected checks run
again, including previously analyzed checks. Test coverage analysis does not
execute tests or measure runtime coverage.

Use the preset picker for saved configurations and **Save preset…** to keep a
new one. Replacing an existing user preset requires **Replace**. Built-ins are
protected. Saving a preset persists it even if you cancel the analysis dialog.

The shared model picker applies to all checks, including disabled checks.
**Customize by check…** exposes individual overrides. **Run details** explains
call grouping and dependencies. Escape closes the active picker/editor first;
otherwise it cancels the dialog. Tab stays within the dialog, and narrow
terminals keep actions visible while the checks scroll.

Design source: [docs/design/review-workspace.md](docs/design/review-workspace.md), [docs/design/impl.md](docs/design/impl.md).
