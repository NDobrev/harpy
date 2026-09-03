# ADR 0007 — Impact rows nest involved files and flag business logic

## Status

Accepted

## Context

An endpoint or schema impact is not useful without the files that carry it,
or a clear answer to whether domain rules changed.

## Decision

- Each `api_impacts` / `db_impacts` item lists `files` and `business_logic`.
- Static enrichment pulls files from the linked logical change and marks
  business logic from `BUSINESS_LOGIC` files, domain, or material `business_impact`.
- The `i` list is a foldable tree: impact row, then involved files. `BL` marks
  business-logic impact. `SEC` marks auth/security impact. The detail pane repeats both.
- Labels are color-coded, not the whole row: cyan `API`, blue `DB`, orange `BL`,
  fuchsia `SEC`, red `⚠`. Impact layout is list | schema | write-up. Selecting a
  file keeps the list on the left and opens the normal file diff in the middle
  (`n`/`p` hunks); the write-up stays on the right.

## Consequences

- Prompt version is part of the cache key (`PROMPT_VERSION=8`).
