# Storage layer

Durable review memory. Legacy JSON/SQLite stores remain for unmigrated TUI
roots. Web and migrated local state use SQLAlchemy repositories.

- Typed repositories only. Application, TUI, and web transport must not write SQL.
- Persist reports, cited excerpts, review actions, and navigation separately from cache.
- Shared decisions/notes are versioned and tenant-scoped. Personal sessions are not.
- Reports are immutable after insert. Lookup uses the report row, not latest-report.
- `cache clean` must not delete reports or human review work.
- A corrupt database is an error. Never replace it with an empty file.
- Do not import `harpy.web`.
