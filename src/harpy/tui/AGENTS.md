# TUI layer

Textual presentation only. Import `harpy.analysis.pipeline`, `harpy.models`, `harpy.review_scope`, and `harpy.prefs`. Never import `harpy.semantic`, `harpy.storage`, `harpy.evidence`, `harpy.github`, `harpy.verification`, or `harpy.git`. Never call `cursor-agent`.

- Responsive workspace: navigator, evidence/content canvas, decision/context inspector.
- Width ≥140 columns: three regions. 100–139: inspector as a drawer. <100: one active pane with tabs.
- Static results render first. Semantic analysis does not start until `s` confirms a scope.
- `e` expands the full file diff. The original diff is always reachable.
- Existing shortcuts remain aliases where practical. Keybindings live in `app.py`.
