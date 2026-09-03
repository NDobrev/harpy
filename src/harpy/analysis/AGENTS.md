# Analysis layer

Deterministic signals, classification, symbols, references, scoring, pipeline orchestration.

- `scoring.py` may import `harpy.models` and stdlib/pydantic only.
- Classifier returns probabilities, not booleans.
- Scoring weights come from config, not hardcoded call sites.
- Reference search: prefer `rg`, fall back to `GitLsFilesSearcher`. Filter hits with import facts when present.
- `syntax/` is tree-sitter only. It must not import `harpy.tui` or `harpy.semantic`.
- Pipeline may call github, git, semantic, cache. TUI must not live here.
