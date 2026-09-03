# TUI layer

Textual presentation only. Import `harpy.analysis.pipeline`, `harpy.models`, `harpy.review_scope`, and `harpy.prefs`. Never import `harpy.semantic` or call `cursor-agent`.

- Three panes: change list, focused diff, context.
- Static results render first. Semantic analysis does not start until `s` confirms a scope.
- `e` expands the full file diff. The original diff is always reachable.
- Keybindings live in `app.py` and match docs/design/impl.md §28.
