---
title: Harpy Web — implementation PRD
status: ready-for-agent
labels: [ready-for-agent]
date: 2026-09-16
version: 1
---

# Harpy Web — implementation PRD

## Document contract and reading order

This is the implementation contract for Harpy's first browser application. It contains the product behavior, technical boundaries, persistence and transport contracts, visual system, operations, delivery sequence, and acceptance criteria. An implementer does not need the planning conversation to understand the requested release.

**MUST** and **MUST NOT** are acceptance requirements. Defaults in this document are decisions, not suggestions. Configurable values may be changed by a deployment operator only where explicitly identified. External deployment inputs such as domains, SSO issuer URLs, credentials, and certificate material are installation inputs, not unresolved product decisions. Do not invent production values for them.

Read sections 1–5 for product behavior; 6–11 for implementation; 12–14 for deployment, migration, and operations; and 15–18 for tests and delivery. The requirement identifiers are stable references for implementation work and acceptance evidence.

This document defines a future implementation. It does not claim that its interfaces or guarantees already exist. Existing TUI tests remain compatibility requirements. Where this PRD intentionally replaces an architectural decision, [ADR 0017](../adr/0017-web-workspace-and-hosted-tenancy.md) records the change. Other existing invariants continue to apply.

Contents:

1. [Problem statement](#1-problem-statement)
2. [Solution, boundaries, and definitions](#2-solution-boundaries-and-definitions)
3. [User stories](#3-user-stories)
4. [Functional specification and parity matrix](#4-functional-specification-and-parity-matrix)
5. [Visual and interaction implementation](#5-visual-and-interaction-implementation)
6. [Architecture and module contracts](#6-architecture-and-module-contracts)
7. [Persistence, identities, and consistency](#7-persistence-identities-and-consistency)
8. [HTTP API and browser routing](#8-http-api-and-browser-routing)
9. [Acquisition, analysis, and job lifecycle](#9-acquisition-analysis-and-job-lifecycle)
10. [Identity, authorization, and credential handling](#10-identity-authorization-and-credential-handling)
11. [Browser/source security and data handling](#11-browsersource-security-and-data-handling)
12. [Configuration, commands, and distributions](#12-configuration-commands-and-distributions)
13. [Migration and compatibility](#13-migration-and-compatibility)
14. [Operations, observability, and recovery](#14-operations-observability-and-recovery)
15. [Testing decisions and acceptance specification](#15-testing-decisions-and-acceptance-specification)
16. [Implementation work packages and dependency order](#16-implementation-work-packages-and-dependency-order)
17. [Release definition of done](#17-release-definition-of-done)
18. [Further notes, defaults, and reference material](#18-further-notes-defaults-and-reference-material)

## 1. Problem statement

Harpy lets developers review a pull request as logical changes rather than an undifferentiated list of files. Its terminal interface serves terminal users, but it limits rich evidence navigation, touch use, visual customization, and browser access for teammates.

Users need the same review capabilities in a browser without learning a different review model, losing stored decisions, or inadvertently starting analysis. Teams additionally need shared decisions and notes, individual identity and inboxes, and dependable behavior when two people edit simultaneously. Organizations must be able to self-host or use a managed service without exposing source or credentials to another organization.

The product principle remains: **compress code volume, not decision information**. A beautiful interface that hides the original diff, evidence limitations, or which revision was analyzed fails this requirement.

## 2. Solution, boundaries, and definitions

### 2.1 Fixed release decisions

| ID | Area | Required decision |
|---|---|---|
| WEB-001 | Review unit | Logical change, with files and hunks subordinate to it |
| WEB-002 | Functional scope | Match all current TUI workflows listed in section 4; do not expose unrelated backend-only roadmap features |
| WEB-003 | Clients | Keep the TUI and CLI; add a React and TypeScript web client using the shared application service |
| WEB-004 | Deployments | Local browser, self-hosted team, and pooled multi-tenant SaaS in the first complete release |
| WEB-005 | SaaS launch | Operator-managed pilot, without public signup, billing, or subscription UI |
| WEB-006 | Team state | One shared decision and one shared note document per report-local logical change; edits have attribution and history |
| WEB-007 | Identity | Existing OIDC SSO for hosted deployments; implicit local identity for loopback mode |
| WEB-008 | Credentials | Administrator-provisioned, per-user GitHub access; organization-provisioned analyzer access |
| WEB-009 | Devices | All review actions work on desktop, tablet, and phone; no keyboard-only features |
| WEB-010 | Themes | White, Black, and Dark Blue; Dark Blue is the initial default |
| WEB-011 | Appearance | Soft raised controls/panels plus restrained neon accents; high-legibility evidence and code |
| WEB-012 | Analysis | Cached/static-first opening; explicit semantic start; read-only analyzer; existing pinned default model |
| WEB-013 | Local source | Laptop working trees in local mode; registered server repositories in hosted mode; no laptop connector |
| WEB-014 | Review continuity | Local TUI and local web share migrated data; local and hosted installations do not synchronize |

### 2.2 Actors and vocabulary

Use the existing domain language. The following definitions make this document self-contained.

| Term | Meaning |
|---|---|
| Logical change | One reviewable product decision spanning one or more files/hunks |
| Hunk | A unified-diff region, with a report-local identifier such as `H1` |
| Review | Durable record of a target: a GitHub PR or a registered local comparison |
| Revision snapshot | Immutable comparison, including resolved base tip, merge base, head commit or content digest, file inventory, and diff |
| Analysis report | Immutable static, semantic, partial, or imported interpretation of exactly one snapshot |
| Source evidence | Citation bound to a snapshot, path, base/head side, captured bytes, and inclusive line range |
| Freshness | Relationship between the selected report and the latest observation of the target; independent of analysis completeness |
| Review decision | Shared human state: unreviewed, reviewed, question, or blocker |
| Scope | Existing semantic check: changes, API, DB, security, questions, tests, omissions; diagrams is a modifier |
| Organization / tenant | Same concept in this release: an isolated team workspace in a hosted installation |
| Membership | User's role within an organization; does not by itself grant every repository |
| Repository grant | Explicit permission for a member to read or review a registered repository |
| Reviewer | Member permitted to read a repository and change its shared review state/start analysis |
| Viewer | Member with read access; cannot change review state or start/cancel analysis |
| Tenant administrator | Manages membership, repository grants, and credential provisioning through the operator interface; source access still requires a grant |
| Platform operator | Deployment operator with infrastructure access, not a normal application role |
| Job | Durable work item for acquisition, metadata refresh, or semantic analysis |
| Personal session | User/interface-specific navigation, selection, filters, and scroll anchors; never a shared decision |

One person may belong to multiple organizations. The organization switcher always shows which organization owns the current screen. Self-hosting initially provisions one organization but uses the same tenant-aware application as SaaS.

### 2.3 Explicitly out of scope

- GitHub review submission, review-thread synchronization, exports, agent handoffs, challenge workflows, verification execution, scenario exploration, architecture maps, cross-PR relationships, and PR split proposals not currently exposed by the TUI.
- New semantic scopes, model providers, scoring formulas, supported source languages, or promises of incremental semantic reuse.
- Public SaaS signup, billing, organization invitation emails, self-service credential connection, or a full administrator web console.
- Desktop packaging, native mobile apps, PWA installation/offline synchronization, notifications, live cursors, collaborative text editing, or merge/rebase actions.
- Synchronizing local and cloud review state, attaching laptop repositories to SaaS, or importing source archives through the browser.
- Running arbitrary commands from a browser, repository configuration, or model output.

Source opening, copy, new browser tabs, responsive diagrams, and team-conflict handling are necessary browser capabilities, not additions to the semantic product scope.

## 3. User stories

1. As a terminal user, I want to open the same local review in a browser so I can choose an interface without losing decisions.
2. As a new reviewer, I want a static review before running AI so I can decide whether analysis is useful.
3. As a returning reviewer, I want cached results immediately so I can resume work while remote services are unavailable.
4. As a reviewer, I want authored, assigned, and requested inboxes based on my GitHub identity so I can find my work.
5. As a reviewer, I want reviews grouped by repository so I can scan multiple projects.
6. As a reviewer, I want repository and open/closed filters to persist so repeated visits remain focused.
7. As a reviewer, I want explicit refresh with timestamps and errors so I know whether metadata is current.
8. As a reviewer, I want logical changes ranked with their scoring inputs so I understand the suggested order.
9. As a reviewer, I want generated/noise changes expandable so compression never hides decision information.
10. As a reviewer, I want files and hunks linked to their logical changes so I can understand cross-file behavior.
11. As a reviewer, I want the full diff and surrounding captured source so I can verify a summary.
12. As a reviewer, I want correct before/after sides and line numbers so evidence remains trustworthy.
13. As a reviewer, I want to inspect API, database, business-logic, and security impact without losing my place.
14. As a reviewer, I want schema, sequence, flow, and blast-radius diagrams to link to source.
15. As a reviewer, I want explicit unavailable and unassessed states so missing analysis is not mistaken for safety.
16. As a reviewer, I want questions, suggested tests, and omissions in persistent lenses so I can act on them.
17. As a reviewer, I want search across titles, paths, symbols, questions, omissions, and notes.
18. As a reviewer, I want keyboard navigation, a command palette, and help so I can work efficiently.
19. As a reviewer, I want stable URLs and back/forward navigation so I can share a precise location with an authorized teammate.
20. As a reviewer, I want to choose analysis checks and models before a run so I control its scope.
21. As a reviewer, I want to save and replace named personal presets intentionally.
22. As a reviewer, I want progress, cancel, and explicit retry so long analysis does not trap me in a modal.
23. As a reviewer, I want an analysis to survive closing the tab so I can return later.
24. As a reviewer, I want a failed analysis to preserve static and completed results.
25. As a reviewer, I want a changed PR head identified without replacing the report I am reading.
26. As a reviewer, I want a shared reviewed/question/blocker decision so the team has one visible disposition.
27. As a reviewer, I want shared notes with author and edit history so the team can preserve reasoning.
28. As a reviewer, I want simultaneous edit conflicts shown explicitly so my work is not silently overwritten.
29. As a reviewer, I want historical decisions to remain tied to their report so a new revision is not implicitly approved.
30. As a reviewer, I want personal navigation separate from shared decisions so teammates do not move my screen.
31. As a phone user, I want to inspect diffs, diagrams, and notes and run analysis using touch alone.
32. As a tablet user, I want drawers and pane switching so the workspace fits my screen.
33. As a keyboard or screen-reader user, I want labeled controls, predictable focus, and non-color status cues.
34. As a user, I want White, Black, and Dark Blue themes without changing review behavior.
35. As a user sensitive to motion, I want static equivalents of neon and loading effects.
36. As a viewer, I want read-only access that clearly explains why mutation controls are unavailable.
37. As a team administrator, I want to provision users and repository grants without exposing credentials to their browsers.
38. As a team administrator, I want revocation to stop access and queued work promptly.
39. As an organization member, I want other organizations unable to discover my source, metadata, jobs, or review history.
40. As a self-hosting operator, I want a documented deployment and backup/restore process using the same application as SaaS.
41. As a SaaS operator, I want bounded per-organization work queues so one organization cannot monopolize the analyzer.
42. As a local user, I want to review committed, staged, and working-tree comparisons without modifying my repository.
43. As an operator, I want actionable health and migration errors rather than silent data replacement.
44. As a maintainer, I want automated parity, isolation, and accessibility checks under the existing acceptance command.

## 4. Functional specification and parity matrix

### 4.1 Existing implementation baseline

The inspected repository already contains Textual browser/workspace/scope screens, a pipeline and ReviewService, Pydantic domain models, Git/GitHub acquisition, scope planning, diagram transforms, review/session helpers, content-addressed files, and both JSON and SQLite storage implementations.

These facts must influence implementation:

- The active storage facade currently selects the JSON implementation; merely having SQLite code does not provide transactional catalog/session writes.
- Browser catalog entries currently point to the newest result. Report lookup can resolve through that mutable catalog. This is not sufficient historical-report storage.
- ReviewService starts work synchronously, uses in-memory run dictionaries, and allocates some review/snapshot identities independently of persistence. Its cancellation token is not propagated through the full semantic invocation chain.
- TUI sessions combine notes/statuses with navigation and save a whole session. They cannot safely serve as shared team records.
- Some TUI full-file rendering reads a worktree path. Web source must come from immutable captured evidence instead.
- Local comparison helpers exist, but the existing generic service entry point assumes a PR-shaped target. Wire local targets deliberately; do not send them to PR resolution.
- The current development Python lacks `_sqlite3`. The web prerequisite and migration behavior must report this clearly; a TUI-only JSON fallback must remain usable before migration.
- Task HP-069 is in progress. Preserve the checks-first scope behavior documented by ADR 0015 and its existing tests; do not assume an unfinished task file is implementation authority.

Do not expose placeholders as finished features. A new endpoint requires working service behavior, persistence, authorization, and tests.

### 4.2 Opening and listing reviews — WEB-020

The browser landing page has five tabs with stable IDs: `local`, `authored`, `assigned`, `review-requested`, and `tracked`.

- `local` means reports stored in this installation/organization, not only filesystem comparisons. Display label: **History**; subtitle: **Reports saved in this workspace**.
- Authored, Assigned, and Requested use the active user's provisioned GitHub identity. The connected login is visible. Never show a service account's results as the user's own.
- Tracked is the deduplicated union of stored reviews and the active user's cached inbox entries, restricted to authorized repositories.
- Inbox metadata and stored report identity remain distinct. Browsing metadata neither clones source nor starts semantic analysis.
- Group by repository, initially collapsed. Expanding a group loads its visible rows. Persist folded groups and disabled repositories personally.
- Open PRs is initially enabled. Turning it off includes closed and merged PRs. Local comparisons are unaffected.
- Rows show repository/PR or comparison label, title, author, updated time, observed and analyzed revisions, completeness, shared reviewed count, and CI summary when known.
- Sort repositories case-insensitively by display name. Within a group sort most recently updated first, then review/target ID for stability. History uses report creation time; unknown times sort last.
- Use cached rows immediately. Refresh is explicit. First use of an inbox without a cache queues metadata retrieval automatically; this is metadata-only work. A failed refresh retains old rows, reports the failure, and shows the cached timestamp.
- Paginate GitHub metadata in pages of 50 to a configurable cap of 500 per tab/refresh. At the cap display **Showing the first 500 results** and a GitHub search link; never imply a complete inbox.
- Missing credentials display a setup-needed state without making the saved authorized History tab unusable.

The Open review action accepts a GitHub PR URL or a registered repository plus positive PR number. Local mode also permits a path registration form. Hosted mode lists only operator-registered local repositories and does not accept a host path from a browser.

In local mode the Open review dialog first resolves an unregistered GitHub URL/name through the local registration endpoint, then opens the returned repository UUID/PR number. Registration is explicit user action, metadata-only, and grants the implicit local user access. Hosted mode never auto-registers an unknown repository and reports that an administrator must register/grant it.

Opening a saved review resolves to an explicit report URL. Opening an uncached target shows an acquisition screen with progress, cancellation, and failure/retry. The first successful acquisition saves and opens a static report; semantic analysis remains manual.

### 4.3 Workspace shell — WEB-021

The shell contains an organization/repository breadcrumb, PR title and source link, analyzed revision, freshness indicator, analysis action/progress, theme/account menu, and three named regions: **Changes**, **Evidence**, and **Inspector**.

The Changes region shows priority-ordered logical changes with status, importance, unexpectedness, confidence, risk, and file count. Rows expand into associated files. Ranking uses the existing server-side formula. Ties use report ordering, then durable change ID. Search and hiding noise filter this list without changing report contents or progress denominators.

The Evidence region contains lens selection and the selected change/file/evidence content. The Inspector shows before/after behavior, consequence, evidence/limitations, shared decision, note, and expandable ranking explanation. Empty fields display **Not assessed** or **None found within assessed context**, never fabricated conclusions.

At all sizes users can maximize a region, restore the layout, switch lens, and return to the browser. Shared events may update badges and status text but must not alter selection, scroll, focus, open editors, or the selected report.

### 4.4 Lenses — WEB-022

| Lens ID | Required content and actions |
|---|---|
| `overview` | Selected change's title, before/after, rationale, consequence, assessed scopes, limitations, counts, and evidence links |
| `diff` | Selected change's hunks, file selection, full-file expansion, source-side controls, ownership labels, and source line links |
| `behavior` | Existing before/after/why fields, with unknown states; no new scenario reasoning |
| `tests` | Existing suggested tests and available test evidence; clearly distinguish suggestions from executed tests |
| `impact` | API/DB entries, business/security markers, associated files, contract details, diagrams, and source navigation |
| `questions` | Existing review questions, with links to their change and available evidence |
| `omissions` | Existing possible omissions plus hunk-accounting coverage and unassessed scope states |
| `history` | Personal navigation history and a separately labeled Shared edit history section for the selected change |

Lens controls remain available when content is empty and explain the reason. Generated/lockfile/snapshot noise has an explicit visibility toggle. It is never permanently removed from the report.

### 4.5 Diff and source behavior — WEB-023

- Default to a unified diff. Desktop split diff is a later enhancement, not required for parity.
- Render separate base/head line-number columns and `+`, `−`, or context markers. A line's citation side is determined by the diff, not its display row.
- Full file means captured head content with deleted base lines inserted at their hunk positions. Deleted files use base content. Preserve the original patch in a separate **Original patch** view.
- Label hunks belonging to the selected change and those belonging to other changes. Shared hunks show every owner; clicking an owner navigates without changing the report.
- Expanded full-file context comes from captured source, not a live checkout. If unavailable, show the entire captured patch plus the specific limitation.
- Renames show old and new paths. Additions/deletions have an absent side. Binary files, submodules, symlinks, unsupported encodings, and oversized sources show metadata and their captured patch/availability reason; do not render fabricated text.
- Source views provide file/side selection, inclusive line anchors, copy visible selection, and copy permalink. Source is not editable. Native browser text selection must work through virtualized rows; a dedicated Copy hunk/file control retrieves complete bounded text independently of mounted rows.
- Initial context is three lines around each hunk. **More context** adds 20 captured lines in each direction; **Full file** requests paged source. Source pages are 200 lines, with a maximum of 1,000 lines and 1 MiB of text per response. A single longer line is returned through bounded character segments, with an explicit continuation control.
- Languages already supported by static analysis remain Python, TypeScript/TSX, Go, Rust, and SQL. Syntax highlighting for other text languages does not imply semantic/static support.
- Tab display width is four columns. Preserve bytes for copy and patch views; never rewrite tabs, CRLF, or missing-final-newline markers in stored content.

### 4.6 Impact diagrams — WEB-024

Render the existing validated schema, sequence, flow, and blast-tree structures as SVG with ordinary accessible HTML controls. Keep a textual/list representation alongside the graphic. Do not execute Mermaid text or arbitrary SVG/HTML supplied by the analyzer.

Reuse existing backend parsers to normalize supported Mermaid fallbacks into those structures. Unparseable input displays escaped text with **Diagram unavailable**, preserving any explanation and source links.

- Schema: old/new tables, added/dropped/changed columns and changed relations; selected impact highlighted without hiding neighboring changed objects.
- Sequence: actor lifelines and ordered messages, before/after labels when present.
- Flow: directed contract steps with edge labels.
- Blast tree: approximate callers/routes/workers/tests; explicitly state that this is not a complete call graph.
- Multiple pictures have Previous/Next, count, and title. Source-linked nodes can be selected by keyboard or touch.
- Use fixed deterministic layout functions: schema grids, sequence lanes, top-to-bottom flow levels, and indented trees. A cyclic flow gets a visible back edge; do not drop cycles or run an unbounded layout algorithm.
- Initially render at most 200 nodes; larger structures have collapsed groups with counts and explicit expansion. All nodes remain available in the list view. Pinch/wheel zoom is confined to the canvas; page scrolling remains available outside it.

### 4.7 Search, palette, and navigation — WEB-025

Search uses case-insensitive normalized text across change ID/title, paths, changed symbols, questions, omissions, and shared notes. Rank exact matches, then prefix matches, then substring matches, preserving report priority within each group. Search is report-scoped and not a regex or an external source search. Debounce by 150ms; discard responses from older queries.

The command palette lists currently available actions, shortcuts, and disabled reasons. `Ctrl/Cmd+K` opens it; `Ctrl/Cmd+P` retains browser print. Keep compatible TUI aliases: `e` expand, `c` noise, `a` all, `i` impact, `s` analysis configuration, `r` questions, `t` tests, `o` omissions, `/` search, `?` help, `z` maximize, `v` reviewed, `Shift+V` reopen, `b` blocker, and `m` note. Add a visible Question status menu item. `q` returns to the review browser and never terminates the server.

Single-letter shortcuts do nothing while typing, while IME composition is active, or inside a dialog unless explicitly part of that dialog. Tab uses normal focus order; F6 cycles the three regions. Escape closes the innermost popover/dialog, then exits maximization; it must not silently discard dirty notes. Browser Back/Forward navigates report/lens/change/source anchors. Filter keystrokes use URL replacement rather than adding history entries.

Each navigation anchor contains report ID, change UUID, file ID, lens, side, optional line, and scroll anchor. Keep 100 personal anchors. On a missing anchor, open the report with a clear **Location no longer available** notice; never substitute evidence from another report.

### 4.8 Analysis configuration — WEB-026

Present grouped checks first, a shared Model picker, optional Customize by check controls, a Preset picker, Save preset, Run details, Cancel, and Start analysis. The footer remains visible while the check list scrolls. Mobile uses a full-screen dialog.

Existing stable scope IDs are `changes`, `api`, `db`, `security`, `questions`, `tests`, `omissions`, and `diagrams`. Diagrams is not an independent call and has no model picker. It is disabled with an explanation when both API and DB are off.

The backend is authoritative for normalization, catalog order, model availability, call grouping, and selection signatures. Calls sharing a model are grouped; the call containing `changes` runs first, followed by remaining groups. Do not reproduce planning rules independently in JavaScript.

Built-in presets are Everything, Security, API, Database, and Fast triage with existing membership. They cannot be renamed/replaced/deleted. User presets are personal within an organization. Name length is 1–80 Unicode characters after trimming; uniqueness is case-insensitive within that user's namespace. An explicit Replace confirmation is required for an existing user preset. Explicit Save preset persists even if analysis configuration is later cancelled. Ordinary selection edits persist only when Start is accepted.

The initial selection is the user's last accepted selection, otherwise Everything using the configured default. Missing legacy fields are normalized by the existing compatibility adapter; new API clients must send all eight enabled flags. Unknown scope IDs fail validation.

Model pickers use the configured model catalog. Preserve a migrated unknown model visibly but disable Start while an enabled check uses a model not permitted by the current deployment. Disabled checks may retain their saved model. Never silently substitute a different model.

Run details show snapshot, selected checks, models, call count, grouping, and **Selected checks will run again, including previously analyzed ones**. No estimated cost, token count, or cache reuse claim unless measured by a future supported provider contract. Start requires at least one actual check and a valid, unexpired server plan. Enter acts on the focused control; Enter inside a picker selects an option, not Start. Escape closes a nested picker before cancelling the configuration dialog.

### 4.9 Freshness, analysis completion, and report selection — WEB-027

Freshness values are `checking`, `current`, `code_changed`, `intent_changed`, `code_and_intent_changed`, `unknown`, and `local_changed`. Show analyzed revision/time and last observation time. A failed metadata request sets observation freshness unknown while retaining the last known revision with its timestamp.

Metadata refresh never replaces the selected snapshot/report or starts semantic analysis. When a different head or intent is observed, show **New revision available** and **Open new static review**. Acquisition of that revision is explicit. An old report can still be analyzed explicitly; the configuration dialog identifies it as historical.

For a run initiated from the current report, automatically navigate to its completed result only when the user is still on that report, has not explicitly switched reports, and has no dirty editor. Preserve a matching change/file and scroll anchor when possible. Otherwise display **Analysis ready — Open result**. Other viewers never switch automatically. All reports remain addressable.

Partial/static fallback remains readable, with failed or cancelled scopes identified. Do not label a non-requested security scope safe, a suggested test executed, or a low-confidence conclusion unimportant.

### 4.10 Shared decisions and notes — WEB-028

Every logical change in a report starts with `unreviewed`, decision version 0, an empty note, and note version 0. The four status choices are Unreviewed, Reviewed, Question, and Blocker. Mark Reviewed is an assignment, Reopen assigns Unreviewed, and Toggle Blocker assigns Blocker or returns an existing Blocker to Unreviewed. Status changes do not modify the note.

Notes are one shared plain-text document per report-local change, at most 20,000 Unicode characters and 80,000 UTF-8 bytes. Existing notes are editable by reviewers with repository write permission. Empty text clears the current note but retains edit history. No rich HTML editor, mentions, or threaded comments in this release.

Decision and note versions are separate so a status change does not conflict with an unrelated note edit. Writes compare the expected version atomically, record actor/time/previous/new values, and increment only when the value changes. A stale write returns 409, including the authorized current value/version. The dialog shows **Your edit** and **Current shared value** with Keep editing, Use current, and Replace with my edit. Replace submits against the displayed current version and may conflict again. No automatic merge or last-write-wins.

Save notes explicitly with Save or Ctrl/Cmd+Enter. While saving, preserve input and show Saving; show Saved only after acknowledgment. An uncertain network result retries the same idempotency key. Navigating away from a dirty editor offers Save / Discard / Keep editing. Reload/close uses the browser's native unsaved-changes prompt where supported; do not promise draft persistence after a browser process dies.

Shared state is bound to `(tenant, review, report, logical-change identity)`. Version 1 deliberately does not carry Reviewed to another report, even for apparently identical code. Show predecessor decision/note history as read-only context when lineage is known. This conservative rule prevents false approval and avoids implying that current lineage heuristics prove equivalence. Session navigation restoration remains independent.

### 4.11 Local comparisons — WEB-029

Register a local repository explicitly. Local registration stores its canonical root and Git common-directory identity. Browser requests subsequently use the repository UUID, never a supplied filesystem root. Hosted registration is operator-only.

Comparison choices are mutually exclusive:

| Mode | Base | Head content | Options |
|---|---|---|---|
| Committed | Merge base of selected base ref and HEAD | Resolved HEAD commit | Required base ref; default suggestion is the configured upstream, otherwise require selection |
| Staged | Resolved HEAD commit | Index blobs | No untracked option |
| Working tree | Resolved HEAD commit | Current tracked working-tree bytes, including staged differences | Include untracked defaults false |

An unborn repository and an unmerged index return a clear unsupported-comparison error. A dirty working tree does not prevent a committed comparison. Never checkout, reset, stash, modify the index, run hooks, follow submodules, or execute external diff/textconv helpers.

Resolve refs to full object IDs before acquisition. Freeze bytes before analysis; compute a canonical manifest/content digest for index/working-tree content. Recheck selected index/worktree metadata and digests after capture; retry capture once if changed, then fail with **Repository changed during capture**. Untracked files, when explicitly included, become real add-file patch entries rather than names appended to a diff. Symlinks are recorded as links and never followed.

## 5. Visual and interaction implementation

### 5.1 Layout measurements — WEB-030

Use CSS pixels, not terminal columns. Desktop is width ≥1200, tablet is 768–1199, and phone is <768. All layouts must work at 320px width and 200% browser zoom.

| Element | Desktop | Tablet | Phone |
|---|---|---|---|
| Header | 64px minimum | 64px minimum | 56px minimum; title can wrap |
| Changes | Initial 280px; resizable 220–420px | 240px; collapsible drawer below 960px | Full active pane |
| Evidence | Flexible, minimum 360px | Remaining width | Full active pane |
| Inspector | Initial 340px; resizable 280–480px | Overlay drawer, width min(420px, viewport−32px) | Full active pane |
| Outer padding/gap | 16px / 16px | 12px / 12px | 8px / 8px |
| Bottom navigation | None | None | 56px plus safe-area inset; Changes / Evidence / Inspector |
| Dialog width | 640px maximum; notes 720px | Viewport−32px maximum | Full-screen, internal scrolling |

If desktop resizing would reduce Evidence below its minimum, clamp the resized region. Persist desktop sizes per user/browser, not per review. Landscape phones use the width breakpoint but keep touch-sized controls. Virtual keyboards must not cover Save/Start: dialogs use dynamic viewport units and a scrollable body. Respect safe-area insets.

### 5.2 Theme tokens — WEB-031

Use the exact initial tokens below. They are starting implementation values; changing one to pass a measured contrast test is permitted only with updated theme snapshots and a recorded explanation. Color never carries status alone.

| Semantic token | White | Black | Dark Blue |
|---|---|---|---|
| `background` | `#EEF1F5` | `#101216` | `#0B1426` |
| `surface` | `#F5F7FA` | `#191D24` | `#142139` |
| `surface-inset` | `#E5EAF0` | `#11151B` | `#0D192D` |
| `surface-raised` | `#FFFFFF` | `#222833` | `#1B2D49` |
| `code-background` | `#FFFFFF` | `#0D1117` | `#09111F` |
| `text` | `#172033` | `#F0F3F9` | `#EDF4FF` |
| `text-muted` | `#4C596D` | `#ABB7C8` | `#B2C2DC` |
| `border` | `#748196` | `#65748A` | `#6B84A7` |
| `accent` | `#006B73` | `#52E8F4` | `#59DDFB` |
| `accent-secondary` | `#6741B5` | `#E79AF8` | `#B5A4FF` |
| `on-accent` | `#FFFFFF` | `#101216` | `#0B1426` |
| `success` | `#17613C` | `#79D8A3` | `#80E1B2` |
| `warning` | `#805000` | `#F5C36B` | `#FFD080` |
| `danger` | `#A3243B` | `#FF93A6` | `#FF9FB1` |
| `addition-background` | `#E7F5EB` | `#142A21` | `#102D2B` |
| `deletion-background` | `#FBECEF` | `#341E27` | `#351F33` |
| `shadow-light` | `rgba(255,255,255,.90)` | `rgba(91,108,133,.14)` | `rgba(108,151,211,.13)` |
| `shadow-dark` | `rgba(124,141,165,.24)` | `rgba(0,0,0,.48)` | `rgba(0,5,17,.55)` |

Derive `focus-ring` from accent; use a solid 2px outline with 2px offset plus optional soft halo. Raised panels use `6px 6px 14px shadow-dark` and `-6px -6px 14px shadow-light`, plus a subtle border. Pressed controls use inset 2px shadows. Do not put a shadow around every diff row. Neon halo is at most 12px blur at 18% accent opacity and is never the only focus indicator.

Corner radii: 16px panels/dialogs, 10px controls, 6px tags. Spacing scale: 4, 8, 12, 16, 24, 32. Use system sans-serif for interface/prose and system monospace for code; no remote fonts. Interface text is 14px minimum on desktop, 16px for phone inputs; code is 13px minimum, user-adjustable to 12–20px. Line heights are 1.5 for prose and 1.55 for code. Headings use 18/24/28px levels, not decorative neon type.

All buttons have normal, hover, focus-visible, pressed, disabled, and loading states. Disabled controls retain a legible label and an adjacent explanation where needed. Status badges have a word/icon as well as color. Changes use `+`/`−`/context markers in addition to backgrounds. The theme gallery must contain real diff, dialog, note-conflict, error, and empty states, not only decorative controls.

Persist the selected theme server-side per user and mirror the non-sensitive theme ID in browser local storage for first paint. Read the mirror before React renders using a bundled bootstrap script. After authentication the saved server preference wins; first-time users get Dark Blue. Sign-out removes identity-specific mirrors, retaining only the theme if the user chooses no privacy-sensitive setting. Do not infer or override an explicitly chosen theme from OS dark mode. No custom-theme editor in v1.

### 5.3 Motion, accessibility, and input — WEB-032

Transitions are 120–160ms opacity/color/shadow only. No pulsing glow or continuous background animation. Reduced-motion disables transitions and replaces animated progress with static state plus elapsed text. No content flashes while changing themes.

Target WCAG 2.2 AA: ordinary text contrast ≥4.5:1, large text ≥3:1, control/focus boundaries ≥3:1 against adjacent colors. Use minimum 44×44px touch targets, including source/diagram actions; tightly spaced source line numbers may use a separate 44px Open line action. Browser zoom and text resizing are supported.

Use semantic landmarks, heading hierarchy, buttons, lists/trees, and labeled form controls. Focus enters and returns from dialogs predictably. Only the topmost modal traps focus. Error text is associated with its field. Progress announcements use a polite live region, throttled to one meaningful update per two seconds; errors use an assertive announcement once. A large list exposes total count and an accessible non-virtualized paginated mode of 50 rows. Diagram text alternatives must convey node/edge labels and source targets.

Loading keeps the shell and prior data visible; do not replace a saved report with a global spinner during metadata refresh. First acquisition has a dedicated progress state. Empty, permission-denied, authentication-expired, stale, partial, cancelled, and server-disconnected states have distinct copy and recovery controls.

## 6. Architecture and module contracts

### 6.1 Selected technology — WEB-040

| Responsibility | Decision |
|---|---|
| Browser | React 19, TypeScript strict mode, Vite; single-page application, no SSR or React server components |
| Browser routing | React Router; browser history, tenant-qualified deep links |
| Remote state | TanStack Query; tenant/user/report-qualified query keys |
| UI state | React component state and small reducers; no second global business-state framework |
| Styling | CSS modules and semantic CSS custom properties; native elements, no pre-styled component suite |
| Virtualization | TanStack Virtual for change lists and diff/source rows |
| Icons | Bundled Lucide SVG icons through React components; no remote icon service |
| HTTP server | FastAPI and Uvicorn, Pydantic boundary models; synchronous database work kept off the ASGI event loop |
| Storage | SQLAlchemy 2 repositories; Alembic schema migrations; SQLite locally and PostgreSQL 18 for hosted installations |
| PostgreSQL driver | Psycopg 3 |
| Jobs | Database-backed queue and worker supervisor; no Redis/Celery dependency |
| Progress/shared updates | Server-sent events with durable per-tenant sequence numbers |
| API type generation | OpenAPI TypeScript generation plus a small typed fetch wrapper |
| Browser tests | Vitest, React Testing Library, Playwright, and axe-core |
| Hosted edge | Caddy TLS/reverse proxy and an OIDC gateway compatible with OAuth2 Proxy |
| Packaging | Python wheel/source archive containing compiled browser assets; Docker Compose for hosted deployment |

Use Node 24 LTS for frontend development/builds and npm with a committed lockfile. End-user local installation requires no Node. Keep Python's existing ≥3.12 requirement. Resolve the latest non-prerelease compatible patch versions when the implementation starts, commit exact Python/npm lock resolution and container image digests, and use those locks in checks/releases. A lock update is reviewed independently; production does not resolve dependencies on startup.

### 6.2 Ownership and dependencies

| Module boundary | Owns | Must not own |
|---|---|---|
| Browser presentation | Layout, gestures, forms, rendering, URL state, accessible interactions | Scoring, semantic call planning, credential selection, filesystem access |
| Web transport | Authentication/session transport, DTO validation, pagination, HTTP/SSE, error mapping, static assets | Direct analyzer/Git/GitHub/storage invocation |
| Application service | Tenant-aware use cases, authorization, target/report selection, state writes, job submission, source queries | UI rendering or HTTP-specific objects |
| Review domain | Logical-change continuity, decisions, notes, conflict rules, search/projections | Semantic execution, subprocesses, transport |
| Analysis workflow | Static/semantic orchestration, scope planning, result validation, report construction | Browser/UI assumptions, verification execution |
| Identity/access | Principals, memberships, repository grants, capability checks | Rendering, GitHub credential persistence in browsers |
| Storage | Transactions, migrations, repository implementations, durable events/queue, artifacts | Semantic analysis or UI logic |
| Worker supervisor | Leases, resource limits, container/process lifecycle, validated result ingestion | Accepting executable commands or paths from a client/model |
| Provider adapters | Existing Git/GitHub/semantic calls via `proc.py`, immutable invocation context | Global environment mutation or tenant inference from cwd |

Web transport may import the application facade, identity interfaces, configuration, and DTO/domain types. Like the TUI, it must not import semantic, storage, evidence, GitHub, verification, or Git implementations directly. New architecture tests enforce both directions: domain/analysis/storage code must not import web/frontend/TUI modules. `subprocess` remains confined to `proc.py`. The worker may use container commands only through that process abstraction. Containers used to host the existing analyzer are not the optional verification runner.

Extract reusable search ordering, scope copy, impact-entry mapping, and diff ownership into presentation-neutral modules reachable through the application facade. Preserve old TUI import names as thin compatibility re-exports where tests or callers depend on them. No React code parses Rich/Textual markup. The API returns structured content and plain text, not rendered terminal strings.

### 6.3 Service interfaces

All hosted entry points require an immutable `RequestContext` containing tenant UUID, actor UUID, role, correlation ID, authenticated subject, and authorization version. It is created by authenticated server code, never deserialized from a browser request. Local callers receive the implicit local context through a compatibility adapter.

The application service exposes these operations; parameter DTOs are defined in sections 7–8:

| Operation | Result and side effects |
|---|---|
| `list_reviews(context, filter, cursor)` | Authorized paginated rows; no remote acquisition or semantic call |
| `refresh_inbox(context, tab)` | Durable metadata job; per-user results |
| `open_target(context, target, idempotency_key)` | Existing explicit report or acquisition job |
| `get_review(context, review_id)` | Target, latest observation, available report summaries, effective capabilities |
| `get_report(context, review_id, report_id)` | Immutable snapshot/report summary plus current shared-state summary |
| `list_changes`, `get_change`, `get_diff`, `get_source`, `get_impacts` | Authorized report-bound projections, paginated where applicable |
| `plan_analysis(context, report_id, selection)` | Expiring immutable plan, normalized selection, digest, planned calls; no execution |
| `start_analysis(context, plan_id, digest, idempotency_key)` | Accepted run handle; saves accepted personal selection in the same transaction |
| `get_job`, `cancel_job` | Durable status/cancellation request; owner/admin rules apply |
| `set_decision`, `save_note` | Atomic versioned mutation and outbox/audit event |
| `load_session`, `save_session` | Personal navigation only |
| `get_preferences`, `update_preferences`, `save_preset`, `delete_preset` | Actor-scoped state; built-in preset protections |
| `events_after(context, sequence)` | Authorized events for a live subscription |

Keep existing synchronous pipeline functions for CLI/test compatibility. They call shared operations or share their core implementation without changing public return types. The new browser job submission API must not wait for semantic completion. For new services, inject repository/provider/clock/process interfaces so tests can drive observable behavior without a live provider.

### 6.4 Frontend state ownership and cache rules

- Server state lives in TanStack Query; query keys begin with deployment/session generation, tenant UUID, and actor UUID. Report data includes report UUID; shared mutations never overwrite immutable report payloads.
- Route state is selected report/change/file/lens/source anchor. URL state outranks saved personal navigation when opening an explicit deep link.
- Modal drafts, focus, active pointer gesture, and unsubmitted search are component state. Do not put source text or notes in local/session storage, IndexedDB, service workers, analytics, or error telemetry.
- On logout, tenant switch, role/grant revocation, or account switch, cancel pending requests, close SSE, clear source-bearing caches, and discard inaccessible drafts after the user has the opportunity to copy their own unsaved text on ordinary logout. Revocation does not allow further source copying.
- Mutation responses identify the updated resource version and event sequence. An event older than the locally applied version is ignored. UI errors preserve the previous authorized data unless authorization was revoked.
- Use optimistic visual feedback only as a labeled pending state. Do not change authoritative reviewed counts until a mutation succeeds.
- Network errors do not cause automatic semantic retries. GET requests retry at most twice with 500ms/1s delay; authentication, permission, validation, and not-found errors are not retried.

## 7. Persistence, identities, and consistency

### 7.1 Storage conventions — WEB-041

Use UUIDv4 generated by trusted application code for durable identifiers. Display `C1`/`H1` only inside their report. Git object IDs are opaque validated Git hashes, not always assumed to be 40 characters. SHA-256 content digests are lowercase 64-character hex strings. Timestamps are UTC ISO 8601/RFC 3339 with a `Z` suffix over HTTP and timezone-aware database values. Versions and event sequences are nonnegative 64-bit integers.

Use SQLAlchemy-defined tables and Alembic migrations for both databases, with explicit dialect-specific PostgreSQL RLS and job-claim SQL. SQLite uses foreign keys, WAL, a five-second busy timeout, and one connection per transaction. Do not share a connection between request/worker threads. PostgreSQL uses short read-committed transactions with atomic compare-and-update writes and row locks for queue claims. No network/provider work occurs inside a database transaction.

Mutable state belongs in database rows. Immutable report/source objects use content-addressed files. A storage reference always includes tenant identity; the digest alone is not an authorization capability. Content keys are computed over exact bytes. Cross-tenant hardlinks/deduplication are prohibited.

### 7.2 Required schema

The following is the minimum schema. Column names/types and constraints are part of the contract. A table may add internal bookkeeping columns without changing the public behavior. Unless stated otherwise, records include `created_at`; mutable records also include `updated_at`. Every tenant-owned table has non-null `tenant_id`, and every tenant-owned foreign key includes it.

| Table | Required columns and constraints |
|---|---|
| `tenants` | `id UUID PK`, `slug text UNIQUE`, `name text`, `state active/suspended/deleting`, `authorization_version bigint default 1`, `limits JSON`, `created_at`, `updated_at` |
| `users` | `id UUID PK`, `issuer text`, `subject text`, `display_name text`; unique `(issuer, subject)`; no email-based identity linking |
| `memberships` | `(tenant_id,user_id) PK`, `role administrator/reviewer/viewer`, `state active/revoked`, `version bigint`; FK to users |
| `repositories` | `(tenant_id,id) PK`, `provider github/local`, `host`, `provider_repository_id nullable`, `display_name`, `local_registration_ref nullable`, `state active/disabled`, `version`; unique tenant/provider/host/provider ID for GitHub |
| `repository_grants` | `(tenant_id,repository_id,user_id) PK`, `permission read/review`, `version`; read is sufficient for a viewer; effective write also requires reviewer/administrator membership |
| `credentials` | `(tenant_id,id) PK`, `kind github/analyzer`, `owner_user_id nullable`, `provider_host`, `ciphertext`, `nonce`, `key_id`, `version`, `state active/revoked`, `verified_login nullable`; one active GitHub credential per tenant/user/host; one active analyzer credential per tenant |
| `reviews` | `(tenant_id,id) PK`, `repository_id`, `target_kind github_pr/local_committed/local_staged/local_working_tree`, `target_key`, `pr_number nullable`, `local_spec JSON nullable`, `latest_report_id nullable`, `last_observation JSON nullable`; unique `(tenant_id,repository_id,target_key)` |
| `snapshots` | `(tenant_id,id) PK`, `review_id`, `base_tip_sha nullable`, `comparison_base_sha nullable`, `head_sha nullable`, `local_digest nullable`, `intent_digest`, `manifest_digest`, `diff_digest`, `acquisition_status complete/limited/legacy`, `captured_at`; at least head SHA or local digest unless legacy |
| `snapshot_files` | `(tenant_id,snapshot_id,id) PK`, `path`, `old_path nullable`, `kind`, `mode`, `base_artifact nullable`, `head_artifact nullable`, `base_available`, `head_available`, `availability_reason nullable`, `binary`, `byte_size`; path uniqueness inside snapshot |
| `reports` | `(tenant_id,id) PK`, `review_id`, `snapshot_id`, `run_id nullable`, `kind static/semantic/partial/legacy`, `schema_version`, `content_digest`, `config_digest`, `scope_summary JSON`, `provenance JSON`; immutable after insertion |
| `logical_changes` | `(tenant_id,review_id,id) PK`, `lineage JSON`; UUID is continuity identity, never automatic approval |
| `report_changes` | `(tenant_id,report_id,change_id) PK`, `review_id`, `local_id`, `rank_index`, `projection JSON`; unique local ID in report; projection supports list/search without loading full blobs |
| `decisions` | `(tenant_id,report_id,change_id) PK`, `review_id`, `status`, `version`, `updated_by`; missing row is version 0/unreviewed |
| `change_notes` | `(tenant_id,report_id,change_id) PK`, `review_id`, `text`, `version`, `updated_by`; missing row is version 0/empty |
| `review_events` | `(tenant_id,id) PK`, `review_id`, `report_id`, `change_id`, `actor_id`, `kind decision/note`, `before JSON`, `after JSON`, `resource_version`, `correlation_id`; append-only |
| `personal_sessions` | `(tenant_id,user_id,review_id,client_kind) PK`, `client_kind web/tui`, `report_id`, `selection JSON`, `history JSON`, `version`; contains no shared note/status map |
| `preferences` | `(tenant_id,user_id) PK`, `theme`, `code_font_size`, `wrap_lines`, `disabled_repositories JSON`, `folded_repositories JSON`, `last_scope_selection JSON`, `version` |
| `presets` | `(tenant_id,user_id,id) PK`, `name`, `normalized_name`, `selection JSON`, `version`; unique `(tenant_id,user_id,normalized_name)` |
| `inbox_cache` | `(tenant_id,user_id,tab,repository_id,pr_number) PK`, `payload JSON`, `credential_version`, `fetched_at`, `error nullable`; tab refresh metadata also records truncation/partial status |
| `analysis_plans` | `(tenant_id,id) PK`, `user_id`, `review_id`, `report_id`, `snapshot_id`, `selection JSON`, `calls JSON`, `config_digest`, `digest`, `expires_at` |
| `jobs` | `(tenant_id,id) PK`, `kind acquire/refresh/analyze`, `review_id nullable`, `snapshot_id nullable`, `actor_id`, `status`, `phase`, `plan_id nullable`, `request_payload JSON`, `dedupe_key`, `cancel_requested_at nullable`, `lease_owner nullable`, `lease_until nullable`, `lease_generation bigint`, `attempt`, `retry_of nullable`, `last_heartbeat nullable`, `result_report_id nullable`, `result_repository_id nullable`, `error JSON nullable`, `usage JSON`, `started_at nullable`, `ended_at nullable` |
| `provider_invocations` | `(tenant_id,id) PK`, `job_id`, `call_id`, `state prepared/started/completed/failed/indeterminate`, `request_digest`, `result_artifact nullable`, `started_at nullable`, `ended_at nullable`, `provider_session_ref nullable` |
| `job_scopes` | `(tenant_id,job_id,scope_id) PK`, `status`, `model`, `result_artifact nullable`, `error nullable`, `completed_at nullable` |
| `event_counters` | `tenant_id PK`, `last_sequence bigint`; locked/incremented inside the mutation transaction |
| `events` | `(tenant_id,sequence) PK`, `type`, `audience_kind user/repository/tenant`, `audience_id nullable`, `review_id nullable`, `report_id nullable`, `job_id nullable`, `resource_version nullable`, `payload JSON`, `created_at`; durable outbox and SSE replay source |
| `idempotency_records` | `(tenant_id,user_id,route_key,key) PK`, `request_digest`, `response_status`, `response JSON`, `expires_at`; same key/different body is a conflict |
| `artifacts` | `(tenant_id,digest) PK`, `kind`, `byte_size`, `storage_key`, `created_at`; links from reports/snapshots/scopes define liveness |
| `admin_audit` | `(tenant_id,id) PK`, `actor_ref`, `operation`, `target_type`, `target_id`, `redacted_detail JSON`, `created_at`; no secrets/source bodies |
| `migration_imports` | `import_id PK`, `source_fingerprint`, `destination_tenant_id`, `state`, `counts JSON`, `validation_digest`, `completed_at nullable`; enables resume/idempotence |
| `legacy_human_work` | `(tenant_id,id) PK`, `import_id`, `original_review_ref`, `original_change_ref`, `kind decision/note/conflict`, `payload JSON`, `reason`, `resolved_at nullable`; preserves unmappable human work without inventing an association |

Foreign keys must prevent a report, job, decision, source file, or artifact reference from combining two tenants. Enforce enum/check constraints in addition to Pydantic validation. Index tenant plus review/report IDs, tenant/user inbox filters, active jobs by status/lease/created time, and events by tenant/sequence. Sensitive validation errors must not disclose another tenant's conflicting key.

Search uses application-normalized fields and tenant/report predicates over report-change projections and current notes. Full-text infrastructure is unnecessary for the fixture size. Pagination is keyset-based, not unbounded offset scans.

### 7.3 Stable target and report identity

- A GitHub target key is provider repository numeric ID plus PR number; a rename updates display metadata without creating another review.
- A local target key includes registered repository UUID, comparison mode, canonical base-ref name for committed mode, and include-untracked flag for working-tree mode. Captured revisions vary under the same review.
- A snapshot represents captured inputs, including title/body intent. Metadata-only intent edits can create a new snapshot even when the code diff is identical.
- A new static or semantic run creates a new report; it never rewrites an existing report. A report contains complete data needed for its projection, not only an empty V2 envelope plus a pointer to a mutable catalog.
- `latest_report_id` is a convenience pointer. Explicit report URLs/lookups must use report rows, never resolve through the latest pointer.
- Do not claim lost historical bytes exist during migration. Legacy reports retain their own captured payload and limitations, and their evidence is limited to what can be verified against those inputs.
- Cross-report logical identity may use the existing identity module. On ambiguity/split/merge allocate distinct UUIDs and record predecessors; no state automatically propagates in v1.

### 7.4 Transaction and event ordering

A decision/note mutation transaction must: authorize current membership and grant; validate report/change association; compare version; change the value; append review history; increment the tenant event counter; append the event; and persist the idempotency response. Commit them together. Publish/stream only committed rows.

If the submitted expected version matches and the value is unchanged, return the current resource without incrementing a version or adding a duplicate history event. If expected version is stale, return 409 even if the text coincidentally matches, unless the idempotency record proves it is a retry of the accepted operation.

Event sequences are strictly increasing within a tenant and allocated under a transactional counter lock, so a later committed event cannot hide an earlier still-uncommitted sequence. Per-user filtering may create sequence gaps; gaps do not imply lost visible data. The API has no global cross-tenant event cursor.

### 7.5 Artifact lifecycle and limits

Write artifacts to an exclusive temporary file under the destination tenant root, verify the SHA-256 and expected length, fsync, and atomically rename before committing referencing rows. An artifact without references is harmless and can be collected after 24 hours. A referencing row with missing/corrupt content is an actionable degraded-data error, never permission to substitute another blob.

Default limits are 20,000 changed files, 100,000 hunks, 50 MiB raw patch, 10 MiB per captured text file, 1 GiB captured text per snapshot, and 250 MiB per report artifact. Exceeding a comparison inventory/patch limit fails acquisition explicitly; exceeding a source-file limit preserves the patch/metadata and records source unavailable. Binary files are recorded with Git identities/metadata and are not copied into text artifacts. Limits can be lowered by a tenant operator; changes do not make previously retained reports disappear.

Capture changed base/head text before static report publication. Capture additional source referenced during semantic inspection before semantic report publication, validating its association with the frozen snapshot. Immutable source material used by published evidence is durable. Worktree cleanup and cache cleanup cannot delete reports, cited source, notes, or decisions.

Default cache retention is 30 days since last use. Durable reports and human work have no automatic age expiry. Event-stream retention is seven days, capped at 100,000 events per tenant; review/admin audit history is retained independently. Idempotency records retain 24 hours; plans expire after 15 minutes. Explicit organization deletion is governed by section 14.

### 7.6 Canonical nested records and enum semantics

JSON columns are typed records validated before insertion, not arbitrary dictionaries accepted from clients. Browser DTOs use the same named structures below. All listed fields are required unless marked optional/nullable; lists default empty only where explicitly stated. Missing information is null or an explicit availability state, not an empty string that could be mistaken for a known value.

| Record | Shape and rules |
|---|---|
| `ScopeSelection` | `enabled`: all eight scope IDs to booleans; `models`: all seven nonmodifier IDs to model strings; `preset`: built-in/personal display name or null; server normalization remains authoritative |
| `ScopeAssessment` | `scope_id`, `status` in not_requested/queued/running/complete/partial/failed/skipped/cancelled, `model` nullable for modifier, `completed_at` nullable, `limitations` string list, `provenance` new/reused/legacy, `source_report_id` nullable |
| `PlannedCall` | `id` stable within plan, `model`, `scope_ids` ordered string list, `stage` 0 for grouping else 1, `context_name` server-generated; never accept context_name as a client path |
| `RevisionObservation` | `head_sha` nullable, `local_digest` nullable, `intent_digest` nullable, `base_tip_sha` nullable, `observed_at`, `freshness` from section 4.9, `error_code` nullable; retain old values with their original observation timestamp on failure |
| `ReviewProgress` | `reviewed`, `question`, `blocker`, `unreviewed`, `total`, `report_id`; integer counts sum to total; exclude unselected historical reports, not filtered/noise changes |
| `CoverageTotals` | `inventory_hunks`, `accounted_hunks`, `supplied_hunks`, `omitted_hunks`, `truncated_hunks`, `unclassified_hunks`; unique hunk IDs, not sum of ownership links; partial/truncated overlaps are documented per entry rather than forced to sum |
| `CoverageEntry` | `hunk_id`, `file_id`, `owner_change_ids`, `supplied_ranges`, `omitted_ranges`, `truncated` boolean, `exclusion_reason` nullable; inclusive old/new-side ranges identify their side |
| `Availability` | `available` boolean, `reason` nullable enum missing_snapshot/absent_side/binary/symlink/submodule/unsupported_encoding/size_limit/legacy_unverified/corrupt/missing_artifact; display explanation is separate plain text |
| `NavigationSelection` | `change_id` nullable, `file_id` nullable, `lens`, `focused_region` changes/evidence/inspector, `side` base/head, `line` nullable positive integer, `scroll_anchor` nullable stable row/node ID, `scroll_offset` nonnegative pixels, `query` ≤256 chars, `hide_noise` boolean |
| `PersonalHistoryEntry` | `report_id`, `change_id` nullable, `file_id` nullable, `lens`, `side`, `line` nullable, `scroll_anchor` nullable, `scroll_offset`; maximum 100 entries |
| `SourceEvidence` | `id`, `repository_id`, `snapshot_id`, `file_id`, `side`, `path`, `blob_digest`, `start_line`, `end_line`, `excerpt`, `excerpt_digest`, `assessment` supported/limited/unsupported, `limitations`; inclusive 1-based range; hash exact excerpt bytes |
| `Claim` | `id`, `change_id`, `kind` observation/inference/question, `statement`, `consequence` nullable, `evidence_ids`, `assessment` supported/limited/unsupported, `limitations`; never imply supported from cached provenance |
| `SafeJobError` | `code`, `message`, `retryable`, `provider_call_started` boolean, `request_id` nullable; no stderr dump or credentials |
| `UsageReceipt` | `duration_seconds` nullable nonnegative number, `calls` nonnegative integer, `repairs` nonnegative integer, `input_tokens` nullable, `output_tokens` nullable, `token_source` measured/estimated/unavailable, `cost` null in v1 |

Job phases are `waiting`, `resolving_target`, `fetching`, `capturing`, `static_analysis`, `preparing`, `analyzing`, `validating`, `persisting`, `stopping`, and `finished`. Phase is explanatory and does not replace durable status. A registration job is kind `refresh` with a trusted `operation=register_repository`; it returns repository identity and no report. A metadata refresh without report acquisition is phase resolving_target/fetching/persisting, never analyzing.

Change score DTOs preserve the current scorer's units: importance and ordinary unexpectedness are finite 0–100 values, confidence is 0–1, and risk is low/medium/high/critical (normalize the existing uppercase enum to lowercase only at the API boundary). Review priority is a finite nonnegative score and is not capped at 100: the default formula `0.7 × importance + 0.3 × unexpectedness` adds 15 when both inputs exceed 70. Configured scoring weights remain authoritative. Do not independently round before sorting; render whole score values and a percentage confidence, with underlying values available to ranking details. If imported dimensions are outside their expected ranges, flag a legacy limitation rather than silently re-score an old report.

An `Impact` contains `id`, `kind` api/db, `change_ids`, `title`, `target`, `before`, `after`, `breaking` true/false/null, `business_logic` boolean, `security` boolean, `file_ids`, `evidence_ids`, `limitations`, and `diagrams`. Unknown breaking status is null, not false. Diagrams are a discriminated union with common `id`, `kind`, `title`, `explanation`, and validated source targets:

- `schema`: old/new table arrays; each table has ID/name, columns with ID/name/type/nullable/default/primary-key flag, and relationships with from/to table/column IDs. Explicit change markers are added/dropped/changed/unchanged. Do not infer missing nullable/default values as false/empty defaults.
- `sequence`: ordered actors with ID/label and ordered steps with ID/from/to/label, optional branch label, and evidence IDs. Preserve repeated calls and explicit ordering.
- `flow`: nodes with ID/label and source targets; edges with ID/from/to/label and evidence IDs; all edge endpoints must exist. Cycles are valid and visibly represented.
- `tree`: rooted nodes with ID/label/kind, source targets, and ordered children; shared references are represented as reference nodes to avoid infinitely recursive cycles.

A diagram source target is `(file_id, side, line nullable, evidence_id nullable)` inside the report's snapshot. Model-supplied absolute URLs are not diagram navigation targets. Validation failures preserve escaped fallback text and a limitation instead of partially executing an unknown diagram representation.

### 7.7 Canonical naming and mutation envelopes

Use `job_id` in HTTP and `run_id` in existing semantic domain adapters; they refer to the same UUID for an analyze job. Do not allocate a second semantic run ID. Acquisition/refresh jobs have no semantic run report provenance. A job may initially have no snapshot; events must keep that field null until a real captured snapshot exists, never fill it with an unrelated placeholder UUID.

Preference defaults are theme dark_blue, code font 13, wrap_lines false, empty disabled/folded repository lists, and default Everything scope selection. Theme enum wire values are `white`, `black`, and `dark_blue`. Navigation defaults are overview lens, Changes focused, head side, no line, empty query, noise visible. The initial selected logical change is the first ranked visible change; a zero-change report has null selection.

All versioned PUT/PATCH requests contain `expected_version` as a nonnegative integer and resource fields specific to that operation. DELETE uses the query value because there is no JSON body. New resource creation has expected version 0 where applicable; existing resources increment monotonically and never reset after clearing content. Resource replies include `version` and `last_sequence` so SSE replay can be reconciled.

Preset preferences, sessions, and layout are personal. On a cross-tab personal-session conflict, prefer the currently visible tab's explicit selection only after refetching and resubmitting; retain another interface's session under its separate client_kind. Preference edits merge only fields explicitly edited against their latest version; an actual same-field collision uses the ordinary conflict response. Do not overwrite an entire preferences record from a stale form.

## 8. HTTP API and browser routing

### 8.1 Common transport rules — WEB-042

All application endpoints start with `/api/v1`. Tenant endpoints below are relative to `/api/v1/tenants/{tenant_id}`. Tenant IDs are UUIDs; slugs appear only in browser navigation. Server membership validation, not possession of a UUID, selects the authorized tenant.

JSON uses snake_case fields and UTF-8. Strict new request models reject unknown fields. Dates and UUIDs follow section 7. JSON responses never contain host paths, credential material, raw provider prompts, unredacted stderr, database connection details, or internal exception traces.

Every response includes `X-Request-ID`. API responses and HTML use `Cache-Control: no-store`; fingerprinted public JS/CSS assets use one-year immutable caching and contain no deployment secrets. Do not enable cross-origin application API access. Same-origin writes require a CSRF header validated against the authenticated session and Origin checks, including local mode.

Collection responses have `items`, `next_cursor` (string or null), and `as_of` (UTC time). Default limit is 50, maximum 200 unless a specific endpoint states otherwise. Cursor values are opaque server-signed encodings bound to tenant, actor where personal, filters, sort key, and optional report/version. Invalid or mismatched cursors return 400 `invalid_cursor`. Lists may include `truncated` and `warnings` when an upstream limit applies; counts identify whether they are total or known-only.

Errors have a top-level `error` object with `code`, safe `message`, `request_id`, `retryable`, and optional `details`. Field failures use `details.fields` containing field name and message. Do not return raw Pydantic input values for credential or source fields.

| HTTP status | Meaning / representative code |
|---|---|
| 400 | Invalid cursor, malformed query, unsupported comparison |
| 401 | `authentication_required` / `session_expired` |
| 403 | Known authorized resource but action forbidden, CSRF failure |
| 404 | Resource absent or outside tenant/repository access; indistinguishable response |
| 409 | `version_conflict`, `idempotency_conflict`, `analysis_already_running`, `repository_changed`, `plan_stale` |
| 410 | Expired plan or stream cursor reset requirement where applicable |
| 413 | Request/payload limit exceeded |
| 422 | Field/domain validation failure |
| 428 | Required expected version or idempotency key missing |
| 429 | Tenant/user rate or queue limit, with `Retry-After` |
| 503 | Required storage/worker subsystem unavailable; does not hide a provider failure inside a completed job |

Request JSON defaults to a 256 KiB body limit. Search is ≤256 Unicode characters; paths are ≤4,096 UTF-8 bytes; title/labels are ≤1,000 characters at input boundaries. Source data follows its own documented limits. User-provided strings render as text.

Mutations that create jobs or change shared data require `Idempotency-Key`, a client-generated UUID retained across transport retries. Preset/preferences/session updates also require it. Route key includes the operation and resource identity. Save the original response transactionally for replay. Login/bootstrap/logout are excluded. Browser retries never generate a new key for the same uncertain operation.

### 8.2 Required DTOs

| DTO | Required fields and semantics |
|---|---|
| `Me` | `user{id,display_name}`, `memberships[{tenant_id,slug,name,role}]`, `mode local/self_hosted/saas`, `csrf_token`, `session_expires_at`, `version_info`, `capabilities`; no credential secrets |
| `Capabilities` | Effective booleans for read, review-state write, analysis start, job cancel, repo registration; server still checks every action |
| `OpenTargetRequest` | `repository_id`, `kind`, `acquire_latest=false`; PR adds `pr_number`; local adds mode/base_ref/include_untracked according to section 4.11; `acquire_latest=true` explicitly captures the current target even when a prior report exists |
| `OpenTargetResponse` | Discriminator `state ready/queued`; ready includes `review_id,report_id`; queued includes `review_id,job`; both include navigation URL |
| `ReviewSummary` | `review_id,repository_id,target,title,author,pr_state,updated_at,latest_observation,latest_report,review_progress,capabilities`; latest report/observation may be null |
| `ReportSummary` | `report_id,review_id,snapshot_id,kind,created_at,analyzed_revision,scope_statuses,completeness,limitations,change_count,hunk_count` |
| `ReportDetail` | Summary plus snapshot metadata, counts, freshness observation, report-bound lens availability; large diffs/source omitted |
| `ChangeSummary` | `change_id,local_id,title,rank_index,importance,unexpectedness,confidence,risk,file_count,hunk_count,noise,status,decision_version,note_present` |
| `ChangeDetail` | Summary plus before/after/why/consequence, paths/file IDs, hunk IDs, symbols, questions/tests/omissions, evidence/impact IDs, scope limitations, current decision/note with versions |
| `DiffPage` | `report_id,file_id,mode focused/full/patch,rows,next_cursor,limitations`; each row has stable row ID, kind, base/head line or null, text segment, continuation flag, hunk ID, owner change IDs |
| `SourcePage` | `snapshot_id,file_id,side,blob_digest,available,reason,start_line,lines,next_cursor`; line records contain number, text, continuation offset/flag; no host path |
| `DecisionResource` | `status,version,updated_at,updated_by`; missing row is explicit default version 0 |
| `NoteResource` | `text,version,updated_at,updated_by`; missing row is explicit default version 0 |
| `AnalysisPlanView` | `plan_id,review_id,report_id,snapshot_id,digest,selection,calls,call_count,expires_at,warnings,rerun_selected=true` |
| `JobView` | `job_id,kind,status,phase,review_id,snapshot_id,actor,scope_statuses,started_at,ended_at,cancel_requested,result_report_id,result_repository_id,error,usage,last_sequence`; IDs not yet allocated or inapplicable are null; registration jobs also return parsed PR number when present |
| `PersonalSession` | `review_id,client_kind,report_id,selection,history,version`; selection uses stable IDs and lens/side/line/scroll, not source text |
| `Event` | `sequence,type,created_at,review_id,report_id,job_id,resource_version,data`; unnecessary nullable IDs omitted |

DTO `completeness` is a structured count/status, not an unsupported percentage of semantic correctness. `usage` reports actual call count, repair count, duration, and token measurement provenance; unavailable cost/tokens are null. No fabricated percent-complete for a provider call.

### 8.3 Endpoint inventory

| Method / route | Request | Response / behavior |
|---|---|---|
| `GET /api/v1/me` | Authenticated context | Me; issues/refreshes CSRF material |
| `POST /api/v1/auth/local` | One-time bootstrap token | Local session cookie; token consumed atomically |
| `POST /api/v1/auth/logout` | CSRF | 204; invalidate local session or initiate hosted gateway logout |
| `GET /repositories` | cursor, query | Authorized registered repositories with kind and capabilities |
| `POST /repositories/local` | Canonicalizable path, local mode only | 201 registered repository; requires implicit local administrator |
| `POST /repositories/github` | `locator` as HTTPS PR/repository URL or owner/name; local mode only | 202 metadata JobView; completed job includes `result_repository_id` and optional parsed `pr_number`; creates registration/grant, never clones or analyzes |
| `GET /reviews` | tab, repo_id, open_only=true, cursor | ReviewSummary page from stored/cached metadata only |
| `POST /inbox/refresh` | tab, open_only | 202 JobView; personal metadata refresh |
| `POST /reviews/open` | OpenTargetRequest | 200 ready or 202 queued OpenTargetResponse |
| `GET /reviews/{review_id}` | None | Review metadata and capability summary |
| `POST /reviews/{review_id}/refresh` | None | 202 metadata/local-observation JobView; no snapshot acquisition |
| `GET /reviews/{review_id}/reports` | cursor | Immutable ReportSummary page, newest first |
| `GET /reviews/{review_id}/reports/{report_id}` | None | ReportDetail; validate review/report association |
| `GET /reports/{report_id}/changes` | query, hide_noise=false, cursor | ChangeSummary page plus unfiltered/filtered counts |
| `GET /reports/{report_id}/changes/{change_id}` | None | ChangeDetail |
| `GET /reports/{report_id}/files` | change_id optional, cursor | Snapshot file metadata plus hunk ownership |
| `GET /reports/{report_id}/files/{file_id}/diff` | change_id optional, mode, cursor | DiffPage |
| `GET /reports/{report_id}/files/{file_id}/source` | side=base/head, start_line=1, limit=200, cursor optional | SourcePage; absent sides are explicit available=false |
| `GET /reports/{report_id}/files/{file_id}/copy` | mode=patch/base/head, hunk_id optional | `text/plain` bounded complete content up to 10 MiB; 413 above limit; no download execution |
| `GET /reports/{report_id}/evidence/{evidence_id}` | None | SourceEvidence plus availability and source anchor |
| `GET /reports/{report_id}/impacts` | change_id optional, cursor | Validated API/DB entries and diagram structures |
| `GET /reports/{report_id}/coverage` | cursor | Coverage entries, totals, exclusions, and unassessed scopes |
| `PUT /reports/{report_id}/changes/{change_id}/decision` | status, expected_version | DecisionResource; 409 includes current resource |
| `PUT /reports/{report_id}/changes/{change_id}/note` | text, expected_version | NoteResource; 409 includes current resource |
| `GET /reports/{report_id}/changes/{change_id}/history` | cursor | Actor-attributed decision/note history, newest first |
| `GET /analysis/catalog` | None | Scopes, descriptions, dependencies, configured model catalog/default, built-in presets, enabled/disabled reason |
| `POST /analysis/plans` | report_id, selection | 201 AnalysisPlanView; no provider invocation |
| `POST /analysis/runs` | plan_id, digest, acknowledge_historical_snapshot=false | 202 JobView; validates plan owner/tenant/config/expiry/historical acknowledgment |
| `GET /jobs/{job_id}` | None | JobView, visible only to authorized job audience |
| `POST /jobs/{job_id}/cancel` | None | 202 while stopping, 200 if already terminal |
| `GET /preferences` | None | Preferences and version |
| `PATCH /preferences` | Changed fields, expected_version | Updated preferences/version; optimistic conflicts |
| `GET /presets` | None | Built-ins plus personal presets; built-ins have stable string IDs, personal IDs are UUIDs |
| `POST /presets` | name, selection | 201 personal preset; name collision 409 |
| `PUT /presets/{preset_id}` | name, selection, expected_version | Explicit replacement; built-in IDs forbidden |
| `DELETE /presets/{preset_id}` | expected_version query | 204; personal only; deleting last-used preset retains saved selection as Custom |
| `GET /reviews/{review_id}/session` | client_kind=web/tui | PersonalSession/default |
| `PUT /reviews/{review_id}/session` | Session fields, expected_version | Versioned personal session; never writes a note or decision |
| `GET /migration/warnings` | cursor | Authorized legacy import warnings and unmapped human-work records; administrators see tenant-wide warnings, local user sees all local records |
| `POST /migration/warnings/{warning_id}/resolve` | Explicit target report/change and chosen value, expected_version, or acknowledge-without-mapping | Reviewer with destination grant; audited mapping/conflict resolution, never deletes original import record |
| `GET /events` | Last-Event-ID header or after query | Authorized SSE stream; one per tab/tenant |

No hosted administrator/credential-secret HTTP endpoints are required in v1. Hosted provisioning is through the operator CLI; the two repository-registration endpoints are restricted to the implicit local administrator. No API accepts arbitrary provider command arrays, environment maps, absolute snapshot roots, model URLs, Docker flags, or shell fragments.

### 8.4 Browser URLs and route recovery

Required routes are `/` (organization selection or redirect), `/o/{slug}/reviews`, `/o/{slug}/reviews/{review_id}`, `/o/{slug}/reviews/{review_id}/reports/{report_id}`, and `/o/{slug}/settings`. The review-only route resolves the chosen/latest saved report once and replaces the URL with an explicit report route.

Report query parameters are `change`, `file`, `lens`, `side`, and `line`; optional browser filters are `tab`, `repo`, `open`, and `q`. Invalid values show a recoverable validation notice and use the report's first available change/default lens. IDs from another report never trigger a global lookup or cross-report substitution. Unknown organization or unauthorized report returns the same not-found screen.

The server serves SPA HTML for known non-API navigation routes, but never for an unknown API route or missing fingerprinted asset. Source links are normal authenticated URLs, not public share tokens. Redirect targets must be same-origin relative paths. A deep link after login returns to the same authorized target.

### 8.5 SSE protocol

Use native EventSource with same-origin cookies/gateway session. Events have an `id` equal to the tenant sequence, an `event` name, and JSON `data` conforming to Event. Types are `job.updated`, `report.created`, `review.observed`, `decision.updated`, `note.updated`, `inbox.updated`, `access.changed`, and `resync_required`.

Data payloads contain IDs/versions and small safe status information, not full notes, source text, provider output, or secrets. Clients invalidate/refetch authorized resources. Events scoped to a user (inbox/preferences) never reach another member. Repository events require current read access. An operator-only global stream does not exist.

Send a comment heartbeat every 15 seconds. Revalidate membership and grants at least every heartbeat and before each event batch; close on session expiry or revocation. Stream access tokens are not placed in URLs. Reconnect uses browser Last-Event-ID, or `after` for a new EventSource created after a deliberate resync. If both exist they must agree.

If the cursor is missing on first connection, return `resync_required` with the current watermark and let the client fetch current visible state. If too old, ahead, or invalid, emit `resync_required` and close. On resync the client obtains the watermark first, refetches visible resources, then reconnects after that watermark so concurrent mutations are replayed. Client version checks discard redundant updates.

Limit event responses to 500 records per read batch and each connection's pending buffer to 1 MiB. Slow consumers are disconnected and replay normally. Reconnect delay starts at one second and caps at 30 seconds with jitter. After three failures, show **Live updates disconnected** and poll active jobs/visible summaries every five seconds while the page is visible. Writes still require normal API acknowledgments. Disable reverse-proxy buffering and compression for SSE; use HTTP/2 at the edge.

## 9. Acquisition, analysis, and job lifecycle

### 9.1 Queue and scheduling — WEB-043

Jobs have durable statuses `queued`, `running`, `completed`, `partial`, `failed`, or `cancelled`, matching the existing RunStatus vocabulary. Cancellation is an independent requested flag while a running job is stopping; the browser displays **Cancelling** without inventing a completed cancellation.

Allowed transitions are queued→running/cancelled and running→completed/partial/failed/cancelled. Terminal jobs never become running again; an explicit retry creates a new job with `retry_of`. Queue retries before provider execution are bookkeeping on the same job, recorded by attempt count. Each transition appends an event transactionally.

Defaults: two global semantic jobs, one semantic job per tenant, one active semantic job per review, four global metadata/acquisition jobs, ten queued semantic jobs per tenant, and two queued semantic jobs per user. Limits are server-controlled. Metadata work must not block behind long semantic jobs. Within a tenant, use FIFO; across tenants, choose the tenant least recently granted a semantic slot, breaking ties by oldest queued job. Claim and capacity checks are atomic across supervisors.

Use PostgreSQL row locking with `SKIP LOCKED` for hosted claims; SQLite uses a short immediate transaction with the same logical rules and a single local supervisor. A lease is 45 seconds; heartbeat every ten seconds. Lease token and generation accompany every result update. A worker holding an expired/replaced lease cannot publish a report or transition the job.

Deduplication keys include tenant, target/review, snapshot, initiating credential identity where acquisition/inbox is personal, plan/config digest, and job kind. For an identical semantic request already queued/running on the same authorized review, return its handle. A different plan on that review returns 409 `analysis_already_running` with its authorized handle. A completed run is not deduplicated into a new explicit rerun; only replaying the same idempotency key returns its previous response.

When starting a job, recheck membership, repository grant, credential state/version, tenant suspension, model policy, queue limit, and plan expiry/config. Do not rely solely on the checks done when enqueuing. Authorization failure makes the queued job failed with a safe reason and zero provider calls.

### 9.2 Opening and acquiring a target

1. Validate target, actor permission, and registered repository. Resolve GitHub URLs only for configured hosts and registered numeric repository identity. Never clone an arbitrary URL from client input.
2. If a stored report exists and no explicit new-revision acquisition was requested, return it immediately. Do not synchronously refresh it or require a working network.
3. Otherwise transactionally create/reuse the review and queue an acquisition job. Multiple callers see one coherent job/report for the same target and credential acquisition identity.
4. The acquisition worker resolves PR metadata and exact base/head hashes using the initiating user's GitHub credential. Fetch only through the established provider adapter; do not execute repository hooks, LFS smudge filters, submodule updates, build scripts, textconv, or external diff programs.
5. Capture comparison base separately from base tip. Construct the complete changed-file/hunk inventory and immutable source artifacts with explicit size/unavailable limits. Local comparisons use section 4.11.
6. Run deterministic static classification, supported syntax facts, signals, references, API/DB impact extraction, and current scoring. Unsupported languages remain text-based; no semantic call occurs.
7. Publish snapshot, static report, projections, and event references atomically after artifact durability. Update latest-report pointer only if this report is not older than a newer published observation/report; never roll the review backwards because an old acquisition finished later.
8. Return completed/partial if readable static data exists. If acquisition cannot establish a trustworthy diff inventory, fail; do not invent an empty successful review. If there are genuinely no changes, publish an explicit zero-change static report with an empty state.

Before semantic execution on a GitHub snapshot, ensure all required source exists in the frozen job workspace. A force-pushed/deleted remote branch cannot redirect the analysis to a new commit. If exact missing objects cannot be fetched, remain static/limited and explain the gap.

### 9.3 Plans and explicit semantic execution

A plan is owned by its actor and tenant and binds review, report, snapshot, normalized checks/models, prompt versions, scoring configuration, trusted analyzer configuration, and intended rerun behavior. Canonical JSON with sorted keys and stable list order produces its SHA-256 digest. Plan creation performs no acquisition or semantic provider call. It may read captured artifacts and local configuration only.

A plan expires after 15 minutes. A model/config/permission change between planning and start makes it stale. New metadata observing another head does not change a plan's frozen snapshot; require the historical-snapshot acknowledgment in the Start request when the current observation differs. Add `acknowledge_historical_snapshot` boolean, default false, to the run request for this purpose. The server derives the need from current observation and rejects missing acknowledgment with 409 `plan_stale` and a reason; the UI preserves selection and reopens details.

On accepted start, persist personal selection and queued job in one transaction, return immediately, and show progress outside the configuration dialog. The provider uses the pinned default `cursor-grok-4.6-high-fast` unless the user chose an allowed per-scope override. Do not change the default-model constants as part of web work.

Selected checks rerun. Unselected previously assessed scopes may be carried into the new report only from the same snapshot and unchanged input/config identity, with explicit provenance and completion timestamps. Unassessed scopes remain unassessed. If `changes` is rerun and changes the grouping, dependent annotations may only carry over when their stable evidence/hunk association validates against the new grouping; otherwise mark them unassessed with a reason. Never attach an old `C1` annotation to a new `C1` by its display label alone.

Execute the group containing `changes` first and persist its completed artifact. Execute other model groups sequentially within a job in v1. This intentionally avoids oversubscribing provider concurrency beneath the tenant limit. Diagrams ride with API/DB. Capture each completed group's structured result before continuing.

Existing bounded parser repair remains: at most one explicit repair call for an invalid provider response, recorded separately in usage. There is no automatic retry of an already-started call on timeout/connection loss/unknown completion. Network preparation before provider start may retry twice with one- and three-second delays if idempotent.

At completion build and validate an immutable report containing complete scope status, claims/changes, evidence, impact structures, hunk accounting, provenance, and limitations. Do not treat a syntactically valid model response as evidence validity. In v1 the existing V1 semantic result may be adapted to the new report envelope, but its limitations and lack of verified citation detail must remain explicit.

### 9.4 Failure, cancellation, and restart

| Trigger | Required durable outcome | Browser recovery |
|---|---|---|
| Missing GitHub credential | Acquisition/refresh fails before remote call; saved reports remain | Setup-needed message; History usable |
| GitHub 401/403 | No automatic credential fallback; preserve cached rows/results | Reprovision/retry instruction |
| GitHub rate limit | Record reset/retry time; no tight retry loop | Cached data and explicit retry after reset |
| Analyzer missing/disabled | Static report remains; analysis start disabled or failed with zero calls | Show installation/configuration reason |
| Provider timeout/crash | Persist completed scopes; partial report if any semantic scope completed, otherwise original static report remains and job fails | Explicit Retry |
| Invalid output after repair | Failed scope and preserved valid scopes; no fabricated success | Limitations and source remain visible |
| User cancellation while queued | Cancelled without provider invocation | Terminal Cancelled state |
| User cancellation while running | Set flag; stop process/container; save validated completed scopes; cancelled job may point to a partial report | Cancelling until confirmed stopped, then inspect partial result |
| Tab closes/device sleeps | Job continues while server/supervisor remains alive | Reopen/subscribe to durable state |
| Server HTTP process restarts | Worker continues; UI reconnects | No duplicate call |
| Worker/supervisor lost before invocation | Reclaim after expired lease; safe preparation may restart | Queued/recovering message |
| Worker lost after invocation began | Reconcile labeled container and completed artifacts; terminate orphan before releasing slot; mark call indeterminate if no durable result | Failed/partial with explicit Retry; never automatic provider repetition |
| Database write fails | Do not acknowledge a save or publish an unreferenced report | Preserve draft; retry with same idempotency key |
| Source artifact missing | Explicit unavailable/corrupt evidence; keep report metadata and human work | Show limitation and operator diagnostic reference |

Cancellation propagates from service to workflow to semantic client to `proc.py` using the same cancel token. For local processes, terminate the process group, wait five seconds, then kill if necessary. For hosted jobs, stop/remove the labeled container with the same grace period. No cancelled/expired lease can publish after cancellation wins the terminal-state transaction. If completion committed first, cancellation returns the completed result without rewriting it.

Graceful local server shutdown stops accepting jobs, requests cancellation for running local jobs, saves completed artifacts, and waits up to ten seconds before force termination. Closing a tab is not server shutdown. Hosted worker shutdown stops claiming, allows up to 30 seconds for graceful completion, then cancels its active containers; deployments may drain longer before sending shutdown.

### 9.5 Hosted worker isolation — WEB-044

Use a trusted supervisor separate from HTTP workers. It prepares a job directory, starts an acquisition/static or semantic container, and ingests validated results. Only the supervisor has container-runtime access. Neither the API nor a job container mounts the runtime socket. The supervisor accepts stored typed jobs, not arbitrary commands received through HTTP.

Container labels include tenant UUID, job UUID, lease generation, and a Harpy-managed marker. A fixed, digest-pinned worker image contains Python/Harpy/Git/gh and the operator-provisioned analyzer binary. Provisioning the analyzer is a documented prerequisite; do not depend on a floating installer at runtime.

Default semantic container limits: non-root user, two CPUs, 2 GiB memory, 256 PIDs, read-only root filesystem, dropped capabilities, no-new-privileges, 256 MiB tmpfs, no host home/SSH agent/socket mounts, and a ten-minute timeout per provider invocation. The total job deadline is 150 minutes: seven groups each allow an initial call and one repair at ten minutes per call, plus ten minutes of preparation/finalization. Actual calls still observe the per-call timeout. Limits are trusted deployment configuration, not PR/browser fields.

Mount only the selected immutable snapshot at `/snapshot` read-only and orchestrator-prepared context at `/context` read-only. Allocate a fresh writable output/scratch directory with a size limit. Prompts and syntax sidecars are prepared by trusted orchestration before analyzer launch; adjust the existing semantic-client adapter so it does not need to write into the read-only snapshot. Analysis output is stdout/declared JSON artifacts, not edits to source. The analyzer invocation retains `--mode ask --trust` and the configured model.

Semantic containers receive only the selected tenant's analyzer credential, never GitHub tokens, database URLs, encryption keys, or other users' home directories. Acquisition containers receive only the initiating user's GitHub credential and permitted repository identity. GitHub credentials are removed before handing captured source to semantic execution.

Use separate acquisition and analyzer egress policies: GitHub host endpoints for acquisition, configured analyzer-provider endpoints for semantic calls. Deny metadata/private-network destinations and unrelated hosts. Implement through the deployed egress proxy/network rules, not a browser-controlled URL allowlist. No repository dependency installation or arbitrary verification occurs. A private GitHub enterprise host requires explicit operator configuration and egress grant.

Job output includes tenant/job/snapshot/lease identity, expected schema version, and artifact checksums. The supervisor verifies identity, size bounds, schema, and evidence/source anchors before importing. Reject paths with traversal, symlinks, device files, or unexpected outputs. Bounded stdout/stderr logs are capped at 5 MiB each; logs shown to users are redacted progress/errors, not raw credential-bearing process output.

## 10. Identity, authorization, and credential handling

### 10.1 Hosted authentication — WEB-045

Deploy Caddy and an OIDC gateway on the public origin; Harpy's HTTP port is reachable only on the private application network. The gateway handles login/callback/session cookies. Harpy accepts a gateway-forwarded ID token only over that trusted connection and independently verifies JWT signature, configured issuer, audience, expiry, and subject. Client-supplied identity headers are stripped at the edge and never trusted alone.

The gateway-to-Harpy token contract is `Authorization: Bearer <OIDC ID token>`. The edge strips any public client Authorization and identity headers before the gateway, and the gateway supplies its verified ID token on every proxied request, including SSE. Configure the gateway's upstream authorization-header support accordingly; an OAuth access token with an unrelated audience is not interchangeable with the ID token. Local authentication does not accept bearer tokens through this path.

The deployment has one configured OIDC issuer and client audience. Organizations requiring different upstream SSO providers use an external identity broker presenting that issuer; implementing a broker is outside Harpy. Membership uses immutable `(issuer, subject)` identity, never a mutable email address/domain claim. A verified login without provisioned membership gets **Access has not been provisioned** and no organization metadata.

JWKS keys are cached for up to one hour, refreshed on an unknown key once, and never fetched from a token-controlled URL. Algorithm allowlist is RS256/ES256; reject `none` and symmetric algorithms. Require 60-second maximum clock skew. SSO sessions have an eight-hour absolute lifetime and 30-minute idle lifetime configured at the gateway; sensitive cookies are Secure, HttpOnly, and SameSite=Lax. TLS is mandatory in hosted modes.

CSRF tokens are random 256-bit session-bound values stored server-side or signed with a deployment secret and bound to authenticated issuer/subject/session expiry. Require `X-CSRF-Token` and a same-origin Origin on every unsafe method. The unauthenticated local bootstrap has its own one-time token check. GET endpoints must not perform mutations except creating ordinary anti-CSRF session material.

The `/me` endpoint returns only memberships of the authenticated user. Selecting a tenant validates membership on every request. Never use an arbitrary `X-Tenant-ID` header without validation. Browser logout clears app state and redirects to the gateway logout endpoint using a fixed same-origin return path; upstream IdP logout behavior is deployment-specific and must be stated in operator documentation.

### 10.2 Local authentication

`harpy web` binds `127.0.0.1` by default on port 8765. If occupied and no explicit port was supplied, try the next ten ports; otherwise fail clearly. Host validation permits only the exact loopback host/port and configured `localhost` alias. Wildcard/LAN binding is rejected in local mode; remote users use hosted mode or a user-managed tunnel to their own loopback server.

On launch generate a cryptographically random 256-bit one-time bootstrap token valid for five minutes. Open a URL with the token in the fragment, never query/path. The bundled bootstrap reads it, immediately removes it using history replacement, then POSTs it to local authentication. A successful exchange creates an HttpOnly SameSite=Strict session cookie bound to this server instance. Local HTTP cookies omit Secure only on loopback. Session lifetime is 12 hours, bounded by process lifetime. Logs never record the token. `--no-open` prints the bootstrap URL deliberately to the user's terminal.

Use no CORS, exact Host validation, Origin/CSRF checks, a locked data directory, and a loopback listener. Possession of a review UUID or reaching localhost is not sufficient to issue writes from an unrelated website. A second `harpy web` pointing to the same data root connects to the running instance through an owner-readable control socket to obtain a fresh bootstrap URL, rather than starting a second local worker scheduler. Stale socket/lock detection checks process identity before recovery.

### 10.3 Authorization matrix

| Action | Viewer + read grant | Reviewer + review grant | Administrator + applicable grant | Platform operator |
|---|---|---|---|---|
| Read reports/source/events | Yes | Yes | Yes | Not through an implicit public bypass |
| Personal preferences/navigation | Yes | Yes | Yes | N/A |
| Refresh own inbox metadata | Yes | Yes | Yes | Provision/diagnose only |
| Acquire an uncached source/create report | No | Yes | Yes | Operator CLI only if explicitly acting for a provisioned identity |
| Change shared decision/note | No | Yes | Yes | No implicit UI impersonation |
| Plan/start semantic analysis | No | Yes | Yes | Provision/diagnose only |
| Cancel own job | No source jobs to cancel | Yes | Yes | Emergency stop through operations |
| Cancel another user's job | No | No | Yes, for a granted repository | Emergency stop |
| Manage tenant members/grants | No | No | Operator CLI with administrator identity | Yes, audited |
| Provision secrets/repos/tenant limits | No | No | Operator CLI, within tenant | Yes, audited |
| Create/delete organization | No | No | No | Yes, audited |

All memberships need a repository grant to see source, including administrators. Role and repository permission combine by the least privilege: a viewer with a mistaken review grant still cannot mutate. Local mode has one implicit administrator and grants for explicitly registered/local existing reviewed repositories.

GitHub permission and Harpy sharing permission are separate: an administrator deliberately grants access to source retained in the organization, even if a particular reader cannot fetch it using GitHub. The UI/admin documentation must state this. Only an initiating user whose GitHub credential can read a target may acquire/refresh that target remotely. Revoking their GitHub token does not delete shared reports or revoke other members' grants.

Source-bearing inbox results are limited to registered/granted repositories before persistence/display. Do not auto-register or share all repositories accessible to a GitHub token. A member's Authored/Assigned/Requested view may therefore be a subset of GitHub; label it **Repositories available in this workspace**.

### 10.4 Tenant enforcement and RLS

Every repository/service method takes the explicit context or tenant ID from a trusted worker context. Missing context is an error, not the local tenant default. The implicit default is allowed only in the local/legacy compatibility adapter.

For PostgreSQL, enable and force RLS on every tenant-owned table. Policies compare `tenant_id` to a transaction-local tenant setting, deny when absent, and apply both read/write checks. Set that value using bound parameters at transaction entry. Do not rely on session-level settings surviving connection pooling. The application/ordinary worker roles must be non-owner, non-superuser, and lack BYPASSRLS. Use a separate migration role for DDL. The global scheduler role may claim jobs/capacity through narrowly scoped routines but cannot read report/source/credential tables; detailed processing opens a tenant-bound transaction.

Global identity bootstrap uses a separately scoped identity repository: it resolves only the verified issuer/subject and returns that user's active membership/tenant display metadata through a narrowly granted database function. It does not expose tenant content or permit a client-selected user ID. This explicit exception makes `/me` and organization selection possible before selecting a tenant without granting the application general RLS bypass. Security-definer helper functions use a fixed search path, typed parameters, and no dynamic SQL; test their grants directly.

Repository grants and personal-row ownership are application authorization checks in addition to RLS. SQLite enforces the same tenant filters and composite foreign keys even though local mode has one tenant; it does not pretend to implement PostgreSQL RLS.

Tenant suspension denies new reads/writes/jobs, disconnects streams within 15 seconds, cancels queued/running work, and prevents publication under revoked authorization. Membership/grant revocation has the same effect for that user/repository; an active job initiated by a revoked user is cancelled. Completed authorized shared reports remain until explicit deletion. Frontend polling or an SSE connection must not extend expired authorization.

### 10.5 Credentials

Provision GitHub tokens and analyzer credentials through `harpy admin` reading from stdin or a protected file, never a command argument echoed into process listings. Validate the GitHub login and allowed host before activation. A failed validation leaves the old credential active; explicit Revoke is separate.

Encrypt stored secret bytes with AES-256-GCM using a random nonce and an external 32-byte deployment master key. Authenticated associated data includes tenant UUID, credential UUID, owner UUID/kind, and credential version, preventing ciphertext substitution. Store only ciphertext, nonce, and key ID in the database. Supply a key ring through an owner-readable mounted secret file; never commit it or place it in frontend assets. Backups require separately protected keys.

A credential update increments its version. New jobs select the current version at execution; a queued job whose planned identity was revoked fails instead of falling back to another user's credential. Rotation without revocation may use the same identity's newer active version after revalidation and records that version. Explicit revocation cancels affected running jobs. Never cache decrypted credentials across tenants or long-lived process-global environment state.

For GitHub, use invocation-local `GH_TOKEN`/configured host and disable ambient gh credential lookup in hosted workers. For analyzer access, the operator provisions the provider-supported environment or credential file into the isolated job only. The application must not invent an OAuth/device flow for the analyzer. Local mode continues to use the user's installed gh/analyzer authentication; hosted mode must never fall back to the operator's home credentials.

Audit provisioning, rotation, and revocation using IDs/login/key version, not secret values. Redact Authorization headers, environment secrets, credential file content, and provider session tokens from errors. Do not return encrypted secret blobs through any browser endpoint.

## 11. Browser/source security and data handling

### 11.1 Untrusted content — WEB-046

Treat PR titles/bodies, repository files, filenames, model output, diagram text, and shared notes as untrusted display content. Render them as text or a small safe Markdown subset with raw HTML disabled; links permit only HTTP/HTTPS and validated internal routes. External links use `noopener noreferrer`; images in PR/model Markdown are not remotely loaded. No `dangerouslySetInnerHTML` for source/model content and no executable SVG from the provider.

Use a production CSP with `default-src 'none'`, `script-src 'self'`, `style-src-elem 'self' 'nonce-<per-response nonce>'`, `style-src-attr 'unsafe-inline'`, `font-src 'self'`, `img-src 'self' data:`, `connect-src 'self'`, `worker-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'none'`, and `form-action 'self'`. Hosted mode also uses `upgrade-insecure-requests`; local HTTP mode omits it. The narrow style-attribute allowance supports React virtualization/positioning; no user/model content becomes CSS or an HTML style attribute. Nonces are random per HTML response and are only for trusted generated style elements. Script policy has no unsafe-inline/unsafe-eval exception. Disable source maps in public artifacts; retain private source maps only for developer builds. Do not embed runtime secrets in Vite environment variables.

Repository paths are canonical relative POSIX paths. Reject absolute paths, drive prefixes, NUL, backslashes, empty/dot/dot-dot components, and percent/double-decoding traversal at the HTTP boundary. Resolve by stored file/evidence ID wherever possible rather than joining a requested path. Do not follow symlinks or submodule pointers to the host. A base/head request must belong to the specified report's snapshot.

Git commands use argument arrays via `proc.py`, resolved object IDs, disabled external helpers/hooks, and trusted registration paths. Revisions beginning with option syntax are never passed through unchecked. Repository configuration may influence presentation/scoring only through validated allowlisted inputs; executable commands, credential endpoints, path roots, models, worker limits, and egress are trusted-user/operator configuration only.

### 11.2 Browser/server caching and privacy

Store no source/report/note content persistently in the browser. Memory caches are cleared on logout/tenant switch/revocation. Non-sensitive theme and layout geometry are the only local-storage values. A disconnected page may retain already-loaded authorized content in memory until its authorization expires; mutation controls show disconnected and do not pretend to save.

No analytics, third-party fonts, image beacons, or CDN script dependencies ship by default. Application access logs record route templates, status, duration, request ID, and permitted tenant/job IDs—not raw URL search values, tokens, note text, source, or model prompts. Error telemetry is disabled by default; enabling an operator sink still uses the redacted schema.

### 11.3 Resource and availability controls

Default HTTP rate limits per authenticated user are 300 reads/minute and 60 writes/minute, with a burst of 30. Analysis start additionally allows five accepted starts/minute and obeys durable queue limits. Cap SSE connections at five per user/tenant. Return 429 with retry delay; do not discard queued work. Local mode retains input size and queue controls but disables request-rate throttling by default.

Gracefully handle provider latency without holding HTTP requests: acquisition/refresh/analysis use jobs. All other requests have a 15-second server deadline; source/list reads target much lower latencies. A health check never triggers a provider call. Protect expensive source/diagram projections with fixed bounds and cache only under tenant/report/input identity.

## 12. Configuration, commands, and distributions

### 12.1 Runtime configuration — WEB-047

Resolve web/server configuration in this order: explicit CLI option, named `HARPY_WEB_*` environment variable, operator-selected TOML file, documented default. A checked-out PR's `.harpy.toml` is never the hosted server configuration file. Local trusted CLI configuration retains existing model precedence (`--model`, `HARPY_MODEL`, trusted config, pinned default), while scope overrides must be allowed by the trusted model catalog.

Server startup validates all configuration before binding a public socket or starting workers. Unknown keys fail validation. Do not silently switch storage engines, authentication mode, or tenant context on invalid configuration. Secrets are supplied through files/stdin, not inline CLI options. Time values are seconds and size values are bytes unless explicitly stated.

| Key / environment suffix after `HARPY_WEB_` | Local default | Hosted requirement/default |
|---|---|---|
| `MODE` | `local` | `self_hosted` or `saas`, explicit |
| `HOST` | `127.0.0.1` | Private interface `0.0.0.0` inside application network; not directly published |
| `PORT` | 8765 with documented fallback | 8000 |
| `PUBLIC_ORIGIN` | Actual loopback origin | Required HTTPS origin with no path/query |
| `DATABASE_URL_FILE` | Generated SQLite URL from data root, no secret file needed | Required protected file containing PostgreSQL URL |
| `DATA_ROOT` | XDG data root for Harpy | `/var/lib/harpy`, persistent |
| `CACHE_ROOT` | Existing Harpy cache root | `/var/cache/harpy`, tenant-partitioned |
| `ARTIFACT_ROOT` | Under data root | `/var/lib/harpy/artifacts`, persistent |
| `WORK_ROOT` | Under cache root | `/var/lib/harpy/jobs`, isolated and bounded |
| `SECRET_KEYRING_FILE` | Not needed for existing local external credentials | Required for supervisor/admin, owner-readable encryption key ring; not mounted into HTTP/job containers |
| `SESSION_SECRET_FILE` | Ephemeral generated per local instance | Required deployment secret for CSRF/session-bound signatures |
| `OIDC_ISSUER` | Disallowed | Required issuer HTTPS URL |
| `OIDC_AUDIENCE` | Disallowed | Required configured gateway client audience |
| `TRUSTED_PROXY_CIDRS` | Empty | Explicit private gateway addresses; never all addresses |
| `WORKER_IMAGE` | Not used for local native execution | Required image reference pinned by SHA-256 digest |
| `EGRESS_PROXY` | Existing local networking | Required hosted worker proxy/policy endpoint |
| `ANALYSIS_CONCURRENCY` | 1 | 2 global default |
| `TENANT_ANALYSIS_CONCURRENCY` | 1 | 1 default; cannot exceed global limit |
| `ACQUISITION_CONCURRENCY` | 2 | 4 global default |
| `TENANT_QUEUE_LIMIT` | 10 | 10 semantic jobs |
| `USER_QUEUE_LIMIT` | 2 | 2 semantic jobs |
| `CALL_TIMEOUT_SECONDS` | 600 | 600; allowed range 30–1800 |
| `JOB_TIMEOUT_SECONDS` | 9000 | 9000; minimum `14 × CALL_TIMEOUT_SECONDS + 600` for the seven-scope maximum |
| `EVENT_RETENTION_SECONDS` | 604800 | 604800 |
| `EVENT_RETENTION_COUNT` | 100000 | 100000 per tenant |
| `CACHE_RETENTION_DAYS` | 30 | 30 |
| `LOG_LEVEL` | `info` | `info`; debug still redacts secrets/content |

Tenant limits and allowed model/provider hosts are operator-managed database configuration, bounded by deployment maximums. Frontend capabilities/catalog read them from the API. Configure content/HTTP limits from sections 7/11 through named keys using the same units; do not create undocumented environment escape hatches.

### 12.2 CLI contract

| Command | Required behavior |
|---|---|
| `harpy web` | Validate prerequisites; migrate if needed; start/reuse loopback instance and local supervisor; open authenticated bootstrap URL |
| `harpy web --no-open` | Same startup, print bootstrap URL and Ctrl+C shutdown instruction |
| `harpy web --port N` | Use exact valid port; occupied port is error |
| `harpy web --repo PATH` | Register/select trusted local repo before opening browser; does not analyze |
| `harpy web --review ID` | Open saved review's explicit report after authentication |
| `harpy serve --config FILE` | Hosted HTTP/static service only; requires explicit hosted mode, PostgreSQL, gateway/auth and artifact configuration |
| `harpy worker --config FILE` | Start supervisor; validates image/runtime/egress/storage; leases jobs until graceful shutdown |
| `harpy db upgrade --config FILE` | Backup as required and apply forward migrations under exclusive migration lock |
| `harpy db import-legacy --source PATH --tenant ID --config FILE` | Validate/import only under explicit operator authorization; dry-run default, `--apply` executes |
| `harpy doctor --web --config FILE` | Redacted runtime checks: SQLite/PostgreSQL availability, migrations, assets, Git/gh/analyzer, worker image, disk, auth config; no semantic invocation |
| `harpy admin tenant create --slug NAME --name NAME` | Create tenant and defaults; no user inferred from email |
| `harpy admin member set --tenant ID --issuer URL --subject SUBJECT --role ROLE` | Provision/update membership, audited; refuses accidental cross-issuer identity linking |
| `harpy admin repo register --tenant ID --github OWNER/REPO` | Resolve numeric identity using an explicitly chosen provisioned actor credential; no implicit source grant |
| `harpy admin repo register --tenant ID --local PATH` | Validate trusted host path and record registration; hosted UI receives ID/display name only |
| `harpy admin grant set --tenant ID --repo ID --user ID --permission read/review` | Set explicit repository grant, audited |
| `harpy admin credential set --tenant ID --kind github/analyzer --user ID --secret-stdin` | Validate/provision; user required only for GitHub; optional `--secret-file` alternative |
| `harpy admin credential revoke --tenant ID --credential ID` | Revoke and cancel affected jobs; never prints secret |
| `harpy admin tenant suspend --tenant ID` | Deny access, cancel jobs, retain data |
| `harpy admin tenant delete --tenant ID --confirm-slug SLUG` | Begin explicit deletion protocol, section 14; exact slug confirmation required |
| `harpy admin backup --destination PATH` | Produce consistent database/artifact manifest backup excluding encryption keys |
| `harpy admin restore --backup PATH --target PATH` | Restore to an empty/offline target only and verify checksums/schema |
| `harpy admin keys rotate --keyring-file FILE` | Re-encrypt secrets under new active key transactionally, then verify decryptability before old-key retirement |

Operator commands require OS/config access and record an explicit operator identity from trusted configuration. They are not exposed as shell execution over HTTP. Exit codes: 0 success, 2 invalid configuration/input, 3 unavailable prerequisite, 4 storage/migration failure, 5 provider/auth failure. Do not include credential values in exception messages or shell completion.

Tenant/member/grant/credential administration also needs `list` and `revoke`/`disable` subcommands returning redacted IDs and states. Read-only output supports `--json`. All administrative mutations require tenant IDs explicitly; there is no current-tenant global state in the operator CLI.

### 12.3 Local distribution

Ship the web dependencies as a Python `web` extra; keep TUI-only installation working. The published wheel and source archive include the compiled frontend bundle. Local runtime must not invoke npm, download fonts/scripts, or build JavaScript. Include a manifest of frontend asset hashes and the matching API schema hash. Missing/mismatched assets produce a startup diagnostic instead of an empty page.

A source checkout uses a documented development command that starts Vite at `http://127.0.0.1:5173` and proxies `/api` to the Python loopback server, preserving same-origin browser requests. The explicit development flag sets the browser public origin to that Vite origin, permits that exact loopback proxy/Host combination, and permits its local HMR WebSocket in CSP. Bootstrap URLs use the Vite public origin. Development exceptions cannot activate in packaged hosted mode; no wildcard development origins are accepted.

Web mode requires functioning Python SQLite support. If `_sqlite3` is unavailable, fail with the detected interpreter path and a specific instruction to install/use a Python distribution with SQLite support, then rebuild the environment. Do not silently use concurrent JSON writes or download a database implementation at runtime. Existing unmigrated TUI-only usage retains its fallback.

### 12.4 Hosted distribution and platform boundary

The supported initial hosted platform is Linux x86-64 with a local rootless Docker-compatible runtime, PostgreSQL 18, and Docker Compose. Local web/TUI support Linux and macOS on existing supported Python installations. Native Windows hosting and hosted multi-region/high-availability are not release requirements.

Compose services are edge TLS proxy, OIDC gateway, HTTP application, PostgreSQL, worker supervisor, and egress proxy. Use fixed internal DNS names. Only edge ports 80/443 are published; PostgreSQL/application/supervisor ports are private. The supervisor alone can control the rootless runtime. Persistent database, artifacts, credential keyring, and operator configuration use distinct volumes/secrets.

The pooled SaaS pilot may run on one host initially; pooling means organizations share the application/database, not that every component must scale horizontally in v1. Multiple HTTP processes are supported because jobs/events/state are durable. All HTTP workers and supervisors on that host share the artifact volume. A multi-host object store/shared-filesystem backend is a later deployment extension; do not claim multi-host support from PostgreSQL alone.

Use the same application image/bundle for self-hosting and SaaS. Deployment mode changes provisioning defaults and tenancy count, not authorization rules. Self-hosted installations initialize one organization. SaaS requires explicit operator tenant creation and capacity planning before onboarding.

## 13. Migration and compatibility

### 13.1 Migration policy — WEB-048

Migrations are forward-only and versioned. Application startup checks compatibility but hosted API/worker processes do not run DDL independently. The operator runs the migration command once under an exclusive lock before new application processes accept writes. Refuse a database newer than the application; never overwrite or silently rebuild a corrupt database.

Before local first migration, stop all old Harpy processes using the root. The launcher checks its known lock/control socket and clearly requires the user to close older instances it cannot coordinate. Old binary versions are unsupported against a migrated root. Preserve a complete backup so rollback means restoring the backup into an independent root, not allowing old code to write beside new data.

The local migration creates an implicit tenant/user and an SQL database in the existing XDG data root. After verification, write an atomic `storage-backend.json` marker identifying SQL backend, schema generation, completed import ID, and minimum compatible application version. Updated CLI/TUI/web entry points consult it. Before marker commit the legacy root remains authoritative; after marker commit SQL is authoritative. Do not dual-write JSON and SQL indefinitely.

### 13.2 Import algorithm

1. Acquire exclusive migration lock and inspect legacy JSON/SQLite/catalog/preset versions. Invalid/corrupt inputs fail with their location; unknown fields may be retained in an import provenance object but must not be silently discarded if they contain human work.
2. Back up metadata and referenced immutable artifacts to a timestamped sibling backup directory with a checksum manifest. Record a source fingerprint in the import table. Never mutate the backup.
3. Create destination tenant/user/repository/review identity mappings. Preserve existing UUIDs where present and valid; otherwise allocate UUIDs and retain a mapping. Report-local `C1`/`H1` labels remain report-local.
   Unattributed legacy history uses a non-login actor named **Legacy import**, scoped in provenance to the destination organization; do not attribute old work to the operator who happened to import it.
4. Import each distinct serialized result/report artifact as an immutable legacy report. Deduplicate by original report ID plus content digest within the tenant, not by PR number or short SHA. Preserve cached-only results as legacy provenance, never promote them to verified semantic cache hits.
5. Import snapshot metadata from trustworthy stored values. If only short revisions/live worktree paths exist, mark legacy acquisition/source limitations. Do not read a current checkout and claim its bytes belong to an old report.
6. Split each saved TUI session: statuses and notes become shared state on the corresponding imported report/change; navigation becomes a TUI personal session. Missing referenced changes are retained as unattached legacy human-work records with a visible import-warning entry, not discarded.
7. If both legacy durable decision events and session state exist, import all history. Resolve the current value from the latest valid timestamp, with session state winning exact ties because it is what the current TUI displayed. If timestamps are missing/contradictory, preserve both and set current status Unreviewed with an import conflict requiring manual resolution. Never infer Reviewed from ambiguous legacy state.
8. Import existing presets/selections/disabled repositories into the implicit user's preferences. Built-in-name collisions become personal names with the suffix ` (imported)` and preserved original name in provenance. Unknown model/scope fields are retained in import warnings; do not silently activate them.
9. Verify counts, artifact checksums, report identity resolution, status/note lengths, and access under the implicit local tenant. Persist import validation summary. Over-limit existing notes remain readable as legacy notes and require shortening only when saved as a new edit; do not truncate imported human work.
10. Commit SQL import and backend marker. Keep legacy files read-only for recovery and document their backup location. A restart resumes an incomplete import using its recorded mapping/fingerprint, or refuses if the source changed since the interrupted import.

Hosted imports are explicit, tenant-qualified operator actions with a dry-run report before `--apply`. Starting SaaS/local web never uploads the developer's local history automatically. Imported per-user navigation/presets require an explicit destination user mapping; shared data belongs to the destination tenant only after operator confirmation.

### 13.3 TUI/CLI compatibility behavior

Keep existing constructors, return types, model defaults, scope signatures, and tested compatibility imports. Introduce new optional context/storage arguments behind adapters. Existing legacy test fixtures can continue to instantiate the fallback in isolated roots. The new browser mode always uses transactional storage.

Update current TUI actions to write decisions/notes through the same versioned operations as web. Loading a legacy-shaped ReviewSession projects shared state plus personal navigation for compatibility, but saving navigation must not replay the entire projected status/note dictionaries into storage. TUI actions retain their loaded decision/note version; conflicts show current versus pending values and preserve the user's text. Unmount saves only personal navigation.

For legacy callers that still call whole-session save, implement a compatibility adapter with a captured baseline and compare only explicitly changed decision/note fields; use expected versions and fail on conflict. A newly created session without a loaded baseline may initialize absent version-0 resources but cannot overwrite existing shared records. Compatibility does not authorize blind upserts.

Continue supporting headless analysis and browsing of persisted results. Do not change old commands to start a web server automatically. Sharing a local database does not make the TUI a remote SaaS client; remote TUI transport is outside this release.

## 14. Operations, observability, and recovery

### 14.1 Health and diagnostics — WEB-049

Expose `/health/live` publicly with only process liveness. `/health/ready` is private and verifies database schema/connectivity, artifact-root access, and compatible bundle; return no credentials or organization list. Worker heartbeat/queue health is a separate private diagnostic so an unavailable analyzer does not make already-saved reviews unreadable.

Structured log fields are timestamp, severity, component, request/job/lease ID, tenant UUID where relevant, safe error code, and duration. Retain no raw source/note/prompt/secret bodies. Record administrative and review edits in their dedicated append-only histories. Standard application logs rotate at 100 MiB/file with ten files by default; deployment log aggregation may replace file rotation.

Metrics include request count/latency/error code, queue depth/oldest age, active jobs, lease expirations, cancellation delay, provider duration/failure category, artifact bytes, database pool saturation, and failed authorization count. Avoid user/review/path IDs as unbounded metric labels. Tenant-specific operational views are authenticated/operator-only.

Warn operators at 80% artifact/disk quota, reject new acquisitions/analyses at 90%, and retain read access plus human-state writes where storage remains available. Default tenant artifact quota is 20 GiB; operators may raise it. Metadata/statistics must not mislabel a storage refusal as a provider failure.

### 14.2 Backup and restore

Default hosted backup is daily, retaining seven daily and four weekly backups. Pause new artifact garbage collection during backup; use a consistent database snapshot and capture the referenced-artifact manifest from that snapshot. Copy and checksum all referenced immutable artifacts. A failed/incomplete copy invalidates that backup and is reported. Backups are encrypted at rest by the operator's backup storage; keys are stored separately and included in the recovery runbook, not in the application archive.

Local backup uses the SQLite backup API while holding the migration/backup coordination lock, then copies the corresponding immutable-artifact manifest. Copying a live WAL database file alone is not a backup. Never back up only the mutable catalog without source/report artifacts.

Restore into an empty offline destination, validate database version/checksums/tenant ownership, reconcile jobs as interrupted, confirm credential decryption with the separately restored keyring, and run read-only health checks before switching traffic. Restore must not resume a started/indeterminate provider call automatically. Pilot objectives are ≤24-hour recovery point and ≤4-hour recovery time for the reference 20 GiB tenant; verify these in a restore exercise rather than advertise an unmeasured SLA.

### 14.3 Organization suspension and deletion

Suspension is reversible and retains durable data. Deletion requires an exact slug confirmation from a platform operator and creates an audit record. Transition to deleting immediately denies access and new jobs; cancel/reconcile all active containers before removing their workspaces.

Delete tenant memberships, grants, credentials, personal state, queue/event rows, reports, snapshots, and tenant artifact/cache/work directories using a tenant-bound manifest, never a client-supplied path. Verify every deleted artifact is under that tenant root. Delete shared user identities only if they have no other memberships and no required retained references; otherwise retain the global identity without the deleted membership.

Retain a minimal platform deletion audit containing tenant ID, operator, timestamps, and counts, but no source, notes, or credential material. Existing backups expire through the documented retention schedule; record the latest expiry date in the deletion report. Restoring a backup must reapply the external deletion ledger before exposing traffic so deleted organizations do not reappear.

### 14.4 Upgrade and rollback

Use a maintenance window for the pilot: stop new job claims, drain/cancel active work, back up, migrate, deploy the matching app/bundle/worker image, verify readiness, then reopen traffic. Do not run old and new schema-writing binaries concurrently unless that migration explicitly declares compatibility. Frontend and API schema hashes must agree; an old open tab receiving `client_upgrade_required` reloads after warning about unsaved edits.

Rollback restores a verified backup and previous matching image, with a visible maintenance notice and disclosure of writes after the backup cutoff. Never apply ad hoc destructive down-migrations. Tenant isolation, authentication, or source-integrity failures block rollout and trigger suspension of affected access until resolved.

## 15. Testing decisions and acceptance specification

### 15.1 Test philosophy and existing prior art — WEB-050

Test observable workflows and invariants through public services, HTTP, and user interactions. Do not write tests that merely repeat a CSS implementation or inspect private method calls. Fakes replace providers, clocks, and process/container adapters, not the domain behavior under test. Use temporary repositories and stored source fixtures.

Existing test families cover TUI browser/workspace/scope behavior, review sessions, static/scoped pipelines, service operations, storage reopen/concurrent writes, source paths, and architecture. Preserve them. Add tests rather than weakening/removing existing expectations. The baseline includes scope configuration not auto-starting, Enter behavior in nested controls, no analysis on inbox open, persistent repository filters, late events not stealing focus, and shared full-file/hunk navigation.

Every module boundary in section 6 needs behavior tests: identity/access, transactional review state, acquisition/source, analysis plans/jobs, provider cancellation, API/SSE, migrations, browser workflows, themes/accessibility, and deployment configuration. Existing test coverage does not substitute for multi-user/multi-tenant cases.

### 15.2 Required automated scenarios

| Test ID | Scenario | Required assertions |
|---|---|---|
| AT-001 | Open saved report | Correct immutable report appears; no acquisition or semantic calls |
| AT-002 | Open new GitHub PR | Acquisition/static report; semantic-call count remains zero until accepted Start |
| AT-003 | First inbox/refresh | Correct personal GitHub identity; no source clone/semantic call; cached errors retained |
| AT-004 | Repository/open-state filters | Persist personally; folded rows and counts correct; no unauthorized repositories |
| AT-005 | Local comparison matrix | Committed/staged/working-tree/untracked behave as specified; branch/index/worktree unchanged |
| AT-006 | Capture race | Detect moving working tree/index, retry once, then fail clearly; no inconsistent snapshot publication |
| AT-007 | Full diff ownership | Shared hunks, other-change links, added/deleted/renamed files, original patch, correct base/head anchors |
| AT-008 | Source unavailable | Binary/symlink/submodule/encoding/oversize/missing blob states explicit; no host-path escape |
| AT-009 | Lens parity | All eight lenses and empty/partial states accessible through click, keyboard, and touch |
| AT-010 | Diagram parity | Four structures, fallback parse, picture cycling, source links, cycles, large collapse, accessible list |
| AT-011 | Search | Exact/prefix/substring ordering over all required fields; stale response ignored; typing does not trigger shortcuts |
| AT-012 | Navigation | Deep links, history, pane focus/maximize, restored scroll; provider/team updates do not steal focus |
| AT-013 | Scope configuration | Built-ins, dependencies, models, per-check overrides, explicit replacement, empty Start disabled, nested Enter/Escape |
| AT-014 | Plan/start | No provider work at plan creation; digest/expiry/model/config/historical checks; accepted preferences saved |
| AT-015 | Queue/idempotency | Duplicate click yields one job; same key/different body conflicts; review serialization and fair tenant limits |
| AT-016 | Progress/reconnect | Ordered authorized events; replay/gaps/reset/slow consumer/poll fallback; no lost visible committed change |
| AT-017 | Cancellation | Queued zero calls; running process actually stops; partials retained; completion/cancel race coherent |
| AT-018 | Worker crash | Lease fencing; orphan reconciliation; started call not repeated; valid completed artifacts recoverable |
| AT-019 | Provider failure | Static/partial data usable; one bounded repair; correct scope statuses and usage provenance |
| AT-020 | Freshness | New code/intent/local observation does not overwrite selected report; unknown distinct from current |
| AT-021 | Decisions | Four statuses, toggle/reopen semantics, independent note version, accurate unfiltered progress |
| AT-022 | Note collision | Two clients edit same version; one success/one conflict; neither draft silently lost; explicit replace rechecks version |
| AT-023 | Uncertain response | Accepted mutation with lost response retries same key and produces one audit event |
| AT-024 | Report revision | New report starts unreviewed; historical decisions/notes preserved; local `C1` does not imply identity |
| AT-025 | TUI/web coexistence | Both observe same SQL state; navigation save cannot overwrite another client's decision/note |
| AT-026 | Personal isolation | Navigation/theme/presets/inbox remain personal while shared decisions broadcast |
| AT-027 | Authentication | Valid OIDC subject membership, unknown user, wrong issuer/audience/algorithm, expiry, logout, spoofed headers |
| AT-028 | Local bootstrap | One-time expiry/replay, Host/Origin/CSRF, no query token, localhost attack page denied |
| AT-029 | Role/repo grants | Read/write/admin matrix enforced; resource IDs from another tenant/repo return indistinguishable 404 |
| AT-030 | Revocation | In-flight stream closes, queued work fails, active work cancelled, frontend clears revoked data |
| AT-031 | Two-tenant adversarial case | Same PR/digests/local labels; no cross-tenant list/source/job/event/artifact/cache/credential access |
| AT-032 | PostgreSQL RLS | Real non-owner role; absent/wrong tenant setting denied; insert/update FK attacks denied; pooled connection reset |
| AT-033 | Credential isolation | Invocation-local secrets only; no ambient hosted fallback; rotation/revocation/audit redaction |
| AT-034 | Worker sandbox | Fake runtime asserts correct image/digest, mounts, limits, no socket/home/DB/GitHub credential in semantic job |
| AT-035 | Browser injection | Malicious PR/note/model/diagram/path strings cannot execute scripts or load remote beacons |
| AT-036 | Legacy import | IDs/content/human work preserved; session split; unknown/ambiguous state visible; interrupted import idempotent |
| AT-037 | Migration failure | Corrupt/newer schema/read-only disk/missing SQLite fail safely; original backup/root intact |
| AT-038 | Theme matrix | Three themes across representative states; measured contrast, no initial flash, no business behavior differences |
| AT-039 | Mobile matrix | 320/390/768/1024px layouts, touch-only full journey, safe areas, keyboard-visible Save/Start |
| AT-040 | Accessibility | Keyboard-only journey, focus trap/return, zoom, live-region throttling, diagram/list alternatives, automated axe checks |
| AT-041 | Large fixture | Pagination/virtualization and latency/memory targets; copied hunk/file not truncated to rendered rows |
| AT-042 | Packaging | Wheel/source archive contain compatible assets; clean install opens local UI without Node/CDN/network |
| AT-043 | Hosted startup | Invalid auth/storage/image/private-network config refuses unsafe startup; saved reports usable if analyzer unavailable |
| AT-044 | Backup/restore/delete | Consistent referenced artifacts, restored job interruption, credential key handling, deletion ledger reapplied |
| AT-045 | Network disconnect | Read current in-memory screen, clearly pending/failed writes, no fake save; reconnect recovers without duplicated analysis |

### 15.3 Browser/device coverage

Playwright runs Chromium, Firefox, and WebKit desktop journeys. Run the core touch journey on emulated iPhone-sized WebKit and Android-sized Chromium, including opening a review, navigating a full diff, opening diagram evidence, marking a decision, editing/conflicting a note, configuring analysis, and reconnecting to progress. Emulation is not claimed to replace real-device testing.

Before pilot release, record manual checks on current iOS Safari and Android Chrome plus an actual keyboard/screen-reader pass. Test at 200% zoom, narrow 320px width, portrait/landscape rotation, reduced motion, and all three themes. Screenshots compare stable seeded fixtures, not timestamps/random IDs. Visual baseline updates are explicit reviewable changes; do not bulk-accept unexplained changes.

### 15.4 Performance acceptance

Use a frozen local fixture of 500 changed files, 2,000 hunks, 100 logical changes, 50 impact entries, and a 10,000-line source file. Reference hardware is four modern CPU cores, 8 GiB RAM, SSD, and a recorded browser/runtime version. Measure 30 warm repetitions after five warmups and report p95; provider/network acquisition is excluded from these application timings.

| Measurement | Target |
|---|---|
| Cached local report navigation to usable Changes/Evidence | <1,000ms p95 |
| Cached change/lens switch | <150ms p95 |
| Report search response including render | <200ms p95 |
| Decision/note save acknowledgment on local/LAN fixture | <250ms p95 |
| API list/change/source projection, server time | <150ms p95 |
| Mounted diff/source rows | ≤300 during ordinary viewport navigation |
| Main-thread blocking task during warmed navigation | No task >100ms |
| Running local cancellation | Process stopped within ten seconds |
| Revoked stream access | Closed within 15 seconds |

For phone-network testing, throttle to 150ms RTT and 1.6 Mbps downstream; a cached server report with cold browser assets should become usable within five seconds using a ≤350 KiB gzip initial JS budget and ≤100 KiB gzip initial CSS budget. Lazy-load diagrams/highlighting and noninitial screens. Display loading feedback within 100ms even when a full response takes longer. Do not fetch a full repository/report blob just to render the navigation list.

### 15.5 Acceptance command and offline setup

`make check` remains the single acceptance command. Extend it to run locked dependency consistency, Python formatting/lint/type/tests/package, frontend formatting/lint/type/unit/component tests, OpenAPI generation drift verification, browser tests, and database integration tests. Formatting/linting in CI check without rewriting.

`make setup` or a separately documented dependency bootstrap may download locked packages, browser binaries, and test prerequisites. `make check` itself must not download anything, call GitHub/a live analyzer, or require a running external database/container daemon. Start a temporary PostgreSQL cluster using preinstalled `initdb`/`pg_ctl` binaries for real RLS/transaction tests, on a temporary Unix socket with outbound network disabled. Require the expected PostgreSQL version before starting. Use preinstalled Playwright browser binaries. Missing prerequisites fail with setup instructions rather than silently skip hosted security tests.

Container orchestration tests use a fake runtime adapter; real hosted smoke/restore exercises are release evidence recorded in section 17, not a reason for default checks to need Docker, external SSO, or a provider. All process invocation helpers continue through the permitted process boundary. Test data uses temporary roots and fixture credentials only. No new tests call cursor-agent unless explicitly marked `cursor`, and those remain excluded from `make check`.

## 16. Implementation work packages and dependency order

These packages are implementation slices, not claims of existing completion or newly created HP task files. When scheduling them, allocate new local task IDs through the repository convention; do not repurpose or edit unrelated existing tasks. Each package must pass the acceptance command and update its own eventual task status/documentation.

| Package | Depends on | Concrete deliverable | Exit evidence |
|---|---|---|---|
| WP-01 Contracts and theme gallery | None | ADR, DTO/OpenAPI skeleton, parity checklist, CSS tokens, responsive seeded gallery with diff/config/conflict states | Schema validation; theme contrast/accessibility checks; no live provider |
| WP-02 Transactional persistence | WP-01 | SQLAlchemy/Alembic tables, tenant-aware repositories, artifacts, history, immutable reports, SQLite/PostgreSQL behavior | AT-021/022/023/024/031/032 storage tests |
| WP-03 Legacy migration and local coexistence | WP-02 | Importer/backend marker, compatibility adapters, TUI versioned decision/note writes, local history preserved | AT-025/036/037 plus unchanged TUI/session suite |
| WP-04 Identity and authorization | WP-02 | Local bootstrap, OIDC adapter, memberships/grants, tenant context, credentials, operator provisioning | AT-027/028/029/030/033 |
| WP-05 Acquisition and immutable evidence | WP-02, WP-04 | PR/local source jobs, snapshot capture, original patches, captured source APIs, static report publication | AT-001/002/003/005/006/007/008/020 |
| WP-06 Analysis execution and events | WP-04, WP-05 | Plans, durable scheduler, cancellation, isolated workers, partial recovery, SSE replay | AT-014/015/016/017/018/019/034 |
| WP-07 First complete web workflow | WP-01, WP-03, WP-05 | Browser → static report → change/diff → decision/note → reload, local packaged entry point | AT-004/007/021/025/042 |
| WP-08 Remaining TUI parity | WP-06, WP-07 | All lenses/diagrams, scope dialog/presets/models, search, palette/help, freshness, navigation | AT-009/010/011/012/013/020 |
| WP-09 Shared-team interaction | WP-06, WP-07 | Broadcast updates, edit attribution/history, collision UI, personal/session isolation | AT-016/022/023/024/026/030/045 |
| WP-10 Full mobile and visual quality | WP-08, WP-09 | All responsive layouts, touch parity, three complete themes, accessibility/performance completion | AT-038/039/040/041 and device evidence |
| WP-11 Hosted distributions and operations | WP-04, WP-06, WP-09 | Compose/SSO/egress deployment, SaaS tenant provisioning, metrics, backup/restore/delete/upgrade runbooks | AT-031/032/033/034/043/044 and hosted exercise |
| WP-12 Release gate | WP-03 through WP-11 | Complete acceptance matrix, clean-install packages, operator/user docs, limitations and restore evidence | All AT scenarios; green `make check`; no open release-blocking defects |

Within WP-07, deliver one functioning vertical workflow before filling every lens. Backend packages must not be marked done merely because their HTTP placeholders return a fixture. UI packages must not be marked done merely because their screenshots look correct. Local preview builds may be used before hosted completion, but the requested v1 release includes all three deployment modes and full mobile functionality.

## 17. Release definition of done

The implementer must produce an acceptance record referencing each WEB/AT requirement, test location, and any manual evidence. No open implementation decision affecting identity, permissions, concurrency, source integrity, or user workflow may be left as a TODO.

Required demonstrations:

1. Install the wheel into a fresh supported Python environment, open local web with no Node, import an existing local review, and observe a TUI decision change in the browser and a browser note change in the TUI.
2. Open a new PR using fake providers in automation and a separately authorized real-provider pilot check; show static results first, select scope/models, explicitly run, navigate source, record decisions, close the browser, and resume.
3. Repeat the complete review workflow on a phone, including diagrams, scope configuration, and a dirty-note conflict.
4. Run a self-hosted organization with two reviewers and a viewer. Demonstrate shared note conflict handling, role enforcement, per-user inboxes, and revocation.
5. Run two SaaS organizations in the same API/database with the same repository/PR fixture. Demonstrate isolated data, credentials, artifacts, events, jobs, and query results under adversarial ID substitution.
6. Interrupt a worker mid-call, reconnect clients, and demonstrate a partial/failed run without silent duplicate provider execution.
7. Refresh a changed head, retain the old report's exact source, open the new static report, and show that Reviewed did not silently propagate.
8. Back up, restore into an empty deployment, validate report/source/note checksums, and demonstrate that deleted-tenant ledger entries remain deleted after restore.

Release artifacts include the Python wheel/source archive with bundled frontend, locked/digest-pinned hosted images, Compose configuration template, local quickstart, SSO/provisioning guide, theme/shortcut/mobile help, migration/rollback guide, operations runbook, and acceptance record. Do not automatically deploy, publish a release, submit a GitHub review, or contact users as a side effect of implementation.

## 18. Further notes, defaults, and reference material

### 18.1 Decisions that must not be reopened accidentally

- Pooled SaaS was explicitly selected over one instance per organization. Do not substitute isolated installations and call the multi-tenant requirement complete.
- Shared team decisions were explicitly selected over personal reviewed state. Personal navigation/presets must not leak into shared state.
- Full phone workflows were explicitly selected over a desktop-only release. Hidden desktop-only commands fail parity.
- Existing SSO and admin provisioning were selected. Avoid expanding v1 into password management, signup/billing, or provider-connection OAuth UI.
- Semantic scope/model behavior stays compatible with the current checks-first TUI; richer UI is not permission to silently start more calls.
- Analysis limits, identity, and secrets are trusted deployment decisions; a repository's config/model text cannot override them.
- The original source/diff and its limitations remain reachable under all themes, screen sizes, and degradation states.

### 18.2 Installer-supplied values

An operator supplies: public hostname/TLS configuration, OIDC issuer/audience/gateway secret, immutable subjects and memberships, repository grants and registrations, per-user GitHub secrets, analyzer binary/credential and provider egress destinations, PostgreSQL connection secret, encryption/session keys, pinned worker image, storage volumes, and backup destination. The application validates their shape/presence. These are credentials/infrastructure facts that cannot be encoded as universal values in a PRD.

The SaaS pilot assumes the operator has an analyzer installation/credential suitable for its hosted use. If that prerequisite is absent, static reviews still work, semantic controls show unavailable, and full release acceptance remains incomplete. Do not work around this by sharing a developer's ambient credentials or changing the pinned provider/model.

### 18.3 External references

These references explain selected mechanisms; this PRD defines Harpy's behavior if an upstream tutorial uses different defaults. Dependencies are resolved and locked as specified in section 6, rather than following a documentation site's floating version automatically.

- [React versions](https://react.dev/versions): React major-version baseline.
- [Vite backend integration](https://vite.dev/guide/backend-integration): serving a built frontend with a separate backend.
- [FastAPI concurrency](https://fastapi.tiangolo.com/async/): separating blocking operations from the ASGI event loop.
- [MDN server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): event IDs, reconnects, and EventSource transport.
- [SQLAlchemy database dialects](https://docs.sqlalchemy.org/en/20/dialects/) and [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/tutorial.html): chosen database/migration mechanisms.
- [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): default-deny policies and privileged-role bypass behavior.
- [OAuth2 Proxy configuration](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/): external OIDC gateway integration.
- [Docker container runtime](https://docs.docker.com/reference/cli/docker/container/run/): explicit resource, mount, network, and privilege controls.
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/) and [Playwright device emulation](https://playwright.dev/docs/emulation): accessibility target and automated device testing.

User-provided visual references are inspiration, not assets to redistribute or an excuse to reduce readability:

- [Easeout neumorphism reference](https://www.easeout.co/images/uploads/neumorphism-ui-design-4.jpg).
- [Neumorphic controls reference](https://img.magnific.com/free-vector/realistic-neumorphic-design-user-interface-elements_52683-54118.jpg?semt=ais_hybrid&w=740&q=80).
- [Neon sign reference](https://img.magnific.com/free-vector/neon-sign-template_1017-7463.jpg?semt=ais_hybrid&w=740&q=80).
- [Dribbble visual reference](https://cdn.dribbble.com/userupload/4276078/file/original-92a45ff7e9108ebfb7d25719c2a69e93.jpg?resize=400x0).

The two Magnific image URLs could not be retrieved during planning. No implementation requirement depends on unseen details in those images; section 5 is the authoritative visual specification.
