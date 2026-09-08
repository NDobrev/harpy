# ADR 0015 — Checks-first scope dialog

## Status

Accepted

## Decision

The scope dialog presents grouped review checks first, a shared model selector,
optional per-check overrides, and a pinned action footer. Presets use explicit
pickers instead of cycling through hidden alternatives. Existing scope IDs,
saved selections, preset membership, and call grouping remain unchanged.

Enter starts analysis only from the check list or Start analysis button. Enter
inside a picker or form acts on that control only. Escape closes nested editors
before cancelling the dialog. Empty selections cannot run. Disabled diagrams
remain visible with their dependency explanation.

The current backend reruns selected checks. The dialog states this explicitly
and reports planned calls rather than unsupported cost or reuse estimates.

## Consequences

- Models and preset names render as plain text.
- Selection edits are saved by the parent only when analysis starts.
- Explicit preset saves persist independently; replacement requires Replace.
- Legacy scope-row helpers remain available for compatibility.
- No analyzer or cache architecture change is part of this redesign.
