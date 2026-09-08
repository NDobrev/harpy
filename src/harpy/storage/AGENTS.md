# Storage layer

Durable review memory. SQLite plus content-addressed files.

- Typed repositories only. Application and TUI code must not write SQL.
- Persist reports, cited excerpts, review actions, and navigation separately from cache.
- `cache clean` must not delete reports or human review work.
- A corrupt database is an error. Never replace it with an empty file.
