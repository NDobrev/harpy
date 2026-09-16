# Web parity checklist

Maps current TUI workflows to the browser workspace. Status values are
`planned` until a later work package delivers the behavior.

| TUI workflow | WEB ID | Web status | Notes |
|---|---|---|---|
| Review browser tabs and repository grouping | WEB-020 | in progress | Inbox refresh is metadata-only; listing UI is later |
| Open saved report without analysis | WEB-020 | in progress | Application service returns the stored report (HP-074) |
| Open uncached GitHub PR | WEB-020 | in progress | Acquisition job publishes a static report (HP-074) |
| Workspace Changes / Evidence / Inspector | WEB-021 | planned | Desktop, tablet, phone layouts |
| Eight lenses | WEB-022 | planned | overview through history |
| Unified diff, ownership, captured source | WEB-023 | in progress | Captured patch/source APIs in HP-074; browser canvas later |
| Schema / sequence / flow / blast diagrams | WEB-024 | planned | |
| Search, palette, shortcuts, deep links | WEB-025 | planned | |
| Checks-first scope configuration | WEB-026 | planned | Gallery includes the dialog chrome |
| Freshness and historical reports | WEB-027 | in progress | New observation does not rewrite a selected report |
| Shared decisions and notes | WEB-028 | planned | Gallery includes conflict UI |
| Local committed / staged / working-tree | WEB-029 | in progress | Capture matrix and race failure in HP-074 |
| Responsive measurements | WEB-030 | in progress | Gallery exercises 320px-class layout |
| White / Black / Dark Blue tokens | WEB-031 | in progress | Tokens and gallery shipped in HP-070 |
| Motion, focus, and accessibility | WEB-032 | in progress | Contrast checks; full a11y in WP-10 |

Backend-only TUI-adjacent work (verification, GitHub submission, exports)
stays out of the first web release.
