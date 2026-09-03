# Domain glossary

Use these terms. Do not invent synonyms in code or docs.

| Term | Meaning |
|---|---|
| Logical change | One product decision spanning one or more hunks/files. The unit of review. |
| Hunk | A unified-diff hunk with a stable id `H<n>`. |
| Blast radius | Approximate set of callers, routes, workers, tests affected by a changed symbol. Not a perfect call graph. |
| Unexpectedness | Distance from stated PR intent plus unrelated-subsystem changes. Independent of importance. |
| Confidence | How complete the evidence is for an AI conclusion. Low confidence does not suppress a high-importance item. |
| Review priority | `0.7 * importance + 0.3 * unexpectedness`, plus a critical boost when both are high. |
| Noise | Generated, lockfile, snapshot, and similar low-decision files. Always expandable. |
| Static signals | Deterministic, weighted evidence computed before the semantic agent. |
| Semantic analysis | Read-only `cursor-agent` grouping and before/after reasoning. Never the sole source of the final score. |
| Degradation | When semantic analysis fails, show static ranking and a banner. The TUI stays usable. |
| API impact | Endpoint/route contract change: before/after, caller impact, breaking or not. Optional mermaid only when the analyzer judges a diagram worth the reviewer's time. |
| DB impact | Schema, migration, or persistence-contract change: before/after, who reads/writes it, breaking or not. Shown in the same `i` impact view as API impact. |
| Schema visualizer | ASCII OLD/NEW table boxes in the impact diagram pane, drawn from `DbChangeImpact.schema_snapshot`. `+` added, `-` dropped, `~` changed. Only relations that changed are drawn. Mermaid is fallback, not the primary picture. |
| Sequence diagram | ASCII lifelines in the impact diagram pane, from structured `sequence` or parsed mermaid. Optional; only when prose hides the call order. |
| Flow diagram | Compact vertical boxes for a contract pipeline. Same pane; mermaid flowchart is fallback. |
| Blast tree | Approximate caller/route/worker/test tree on the impact diagram pane. Built from `ReferenceHit` when the analyzer omits `tree`. Not a perfect call graph. |
| Impact files | Source files involved in an API or DB impact. Nested under that row in the `i` list. |
| Business-logic impact | Domain rules, calculations, or state machines changed because of the contract. Shown as `BL` on the impact row. |
| Security impact | Auth, permission, RBAC, secrets, or data-exposure change. Shown as `SEC` on the impact row. |
| Impact color | Colored labels only in the `i` list: cyan `API`, blue `DB`, orange `BL`, fuchsia `SEC`, red `⚠`. |
| Analyzer | Read-only agent role (`--mode ask`) that inspects a PR head worktree. |
| Builder | Write+shell agent role that implements one `HP-xxx` in an isolated worktree. |
| Review scope | One selectable slice of semantic analysis (`changes`, `api`, `db`, `security`, `questions`, `tests`, `omissions`, `diagrams`). Chosen in the `s` dialog before the agent runs. |
| Scope preset | A named, reusable set of enabled scopes and per-scope models. Built-ins plus user presets in `~/.config/harpy/presets.json`. |
| Scope call | One `cursor-agent` invocation produced by grouping selected scopes that share a model. |
| Syntax fact | Deterministic tree-sitter record (`DEF` / `IMP` / `ROUTE` / `DDL`) for a changed file. Syntax only; not types, not a call graph. |
| Sidecar | `SYMBOL_FACTS.md` in the PR worktree. The analyzer greps it on demand. It is not inlined into the prompt bundle. |
