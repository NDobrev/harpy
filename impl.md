# PRLens — Implementation Plan

## 1. Overview

**PRLens** is a terminal-based pull request review tool designed for repositories with large amounts of AI-generated code.

The core problem it solves is not simply “large diffs.” The harder problem is that AI agents often generate substantial amounts of implementation detail, boilerplate, tests, refactors, and supporting code around a relatively small number of meaningful product or business decisions.

PRLens should help a reviewer answer:

- What are the few changes in this PR that actually matter?
- Which changes affect business behavior?
- Which changes are risky or unexpected?
- What code paths are affected?
- Why was each important change needed?
- What should I inspect first?
- Which parts of the diff are likely implementation noise?
- What important behavior may be missing from the implementation?

The guiding principle is:

> **Compress code volume, not decision information.**

---

# 2. Product Goals

## Primary goals

PRLens should:

1. Fetch a pull request and its diff.
2. Analyze changed code using deterministic/static signals.
3. Use Codex CLI for semantic analysis.
4. Group raw diff hunks into meaningful logical changes.
5. Rank logical changes by review importance.
6. Surface the most important business logic first.
7. Explain the before/after behavior of important changes.
8. Estimate the blast radius of each important change.
9. Surface risk, uncertainty, and unexpected behavior.
10. Allow the reviewer to expand from summarized changes into the real diff.

## Non-goals for V1

V1 should not attempt to:

- replace GitHub's review system;
- perform perfect whole-program static analysis;
- automatically approve or reject PRs;
- fully understand every language;
- create a perfect call graph;
- become a general-purpose IDE;
- run arbitrary autonomous fixes;
- hide code permanently from the reviewer.

Everything hidden or summarized must remain expandable.

---

# 3. High-Level User Experience

Example:

```text
$ prlens 1842
```

The tool opens a TUI:

```text
┌──────────────────────┬───────────────────────────────────┬───────────────────────┐
│ IMPORTANT CHANGES    │ FOCUSED DIFF                      │ CONTEXT               │
│                      │                                   │                       │
│ 96 🔴 Auth semantics │ - if project_admin(user):        │ Risk: HIGH            │
│ 89 🔴 Delete API     │ + if can_admin(user):            │ Confidence: 94%       │
│ 76 🟠 Role fallback  │                                   │                       │
│ 34 🟡 Migration      │                                   │ Before                │
│ 12 ⚪ Tests          │                                   │ Project admins only   │
│  4 ⚪ Generated      │                                   │                       │
│                      │                                   │ After                 │
│                      │                                   │ Org admins also       │
│                      │                                   │ allowed                │
│                      │                                   │                       │
│                      │                                   │ Affects               │
│                      │                                   │ • DELETE /users       │
│                      │                                   │ • Admin UI            │
│                      │                                   │ • cleanup worker      │
└──────────────────────┴───────────────────────────────────┴───────────────────────┘
```

Selecting a logical change should show:

- title;
- importance;
- confidence;
- risk;
- before behavior;
- after behavior;
- reason for change;
- affected components;
- changed symbols;
- relevant files;
- tests covering the behavior;
- possible missing coverage;
- review questions;
- focused diff;
- ability to open the full file diff.

---

# 4. Core Design Principle: Logical Changes Instead of Files

The main unit of review should be a **logical change**, not a file.

A PR may modify:

```text
permissions.py
user_service.py
users_controller.py
users_test.py
permissions_test.py
```

But all of those changes may represent one product decision:

> Allow organization administrators to delete users.

PRLens should group those edits into one semantic change.

Example:

```text
CHANGE C1
Allow organization admins to delete users

Implementation
├── src/auth/permissions.py
├── src/services/user_service.py
└── src/api/users_controller.py

Verification
├── tests/users_test.py
└── tests/permissions_test.py
```

This grouping should be one of the main responsibilities of the Codex analysis phase.

---

# 5. Proposed Technology Stack

## Language

Python 3.12+

## CLI

Recommended:

- `typer`

Alternative:

- `click`

## TUI

Recommended:

- `textual`

Why:

- good multi-pane layouts;
- async task support;
- keyboard navigation;
- scrollable source views;
- reactive state;
- simple modal/detail views;
- built-in widgets;
- Python-native integration.

## GitHub integration

Use the GitHub CLI:

```bash
gh
```

Core commands:

```bash
gh pr view
gh pr diff
gh pr checkout
```

Prefer subprocess calls instead of GitHub API integration for V1.

## AI analysis

Use:

```bash
codex exec
```

Use structured output with a JSON schema.

## Git

Use the local `git` CLI through subprocesses.

## Static code analysis

V1:

- changed-line parsing;
- file metadata;
- extension classification;
- regex/import analysis;
- `rg` / ripgrep reference search;
- simple AST parsing for Python;
- diff statistics.

Later:

- Tree-sitter;
- LSP references;
- language-specific parsers.

---

# 6. Suggested Repository Structure

```text
prlens/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── prlens/
│       ├── __init__.py
│       ├── cli.py
│       │
│       ├── config.py
│       ├── models.py
│       │
│       ├── github/
│       │   ├── __init__.py
│       │   ├── gh.py
│       │   └── models.py
│       │
│       ├── git/
│       │   ├── __init__.py
│       │   ├── repository.py
│       │   ├── worktree.py
│       │   └── diff.py
│       │
│       ├── analysis/
│       │   ├── __init__.py
│       │   ├── pipeline.py
│       │   ├── file_classifier.py
│       │   ├── static_signals.py
│       │   ├── scoring.py
│       │   ├── symbols.py
│       │   ├── references.py
│       │   └── impact.py
│       │
│       ├── codex/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── prompts.py
│       │   ├── schemas.py
│       │   └── parser.py
│       │
│       ├── cache/
│       │   ├── __init__.py
│       │   └── store.py
│       │
│       └── tui/
│           ├── __init__.py
│           ├── app.py
│           ├── screens.py
│           ├── widgets/
│           │   ├── change_list.py
│           │   ├── diff_view.py
│           │   ├── context_panel.py
│           │   ├── impact_tree.py
│           │   └── status_bar.py
│           └── styles.tcss
│
├── schemas/
│   └── codex_analysis.schema.json
│
├── tests/
│   ├── fixtures/
│   ├── test_diff_parser.py
│   ├── test_scoring.py
│   ├── test_classifier.py
│   └── test_codex_parser.py
│
└── examples/
    └── analysis.json
```

---

# 7. Domain Models

Use typed data models everywhere.

Recommended:

- Python `dataclasses`, or
- `pydantic`.

Pydantic is preferable because Codex output will need validation.

## PullRequest

```python
class PullRequest(BaseModel):
    number: int
    title: str
    body: str
    base_ref: str
    head_ref: str
    head_sha: str
    additions: int
    deletions: int
    files: list["ChangedFile"]
```

## ChangedFile

```python
class ChangedFile(BaseModel):
    path: str
    status: str
    additions: int
    deletions: int
    language: str | None

    generated_probability: float = 0.0
    test_probability: float = 0.0
    business_logic_probability: float = 0.0

    hunks: list["DiffHunk"]
```

## DiffHunk

```python
class DiffHunk(BaseModel):
    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    patch: str

    changed_symbols: list[str] = []
    static_score: float = 0
```

## LogicalChange

```python
class LogicalChange(BaseModel):
    id: str
    title: str

    importance: float
    confidence: float
    unexpectedness: float
    risk: str

    business_impact: float
    behavior_change: float
    blast_radius: float
    security_sensitivity: float
    data_sensitivity: float
    novelty: float

    before: str
    after: str
    why: str
    business_effect: str

    files: list[str]
    hunks: list[str]
    affected_symbols: list[str]
    affected_components: list[str]

    review_questions: list[str]
    possible_omissions: list[str]
    tests: list[str]

    domains: list[str]
```

---

# 8. Analysis Pipeline

The main pipeline should be deterministic where possible and use Codex only where semantic reasoning provides value.

```text
PR
 │
 ▼
Fetch metadata
 │
 ▼
Fetch diff
 │
 ▼
Create worktree
 │
 ▼
Parse changed files / hunks
 │
 ▼
Classify noise
 │
 ▼
Extract static signals
 │
 ▼
Identify changed symbols
 │
 ▼
Find references
 │
 ▼
Produce analysis context
 │
 ▼
Codex semantic analysis
 │
 ▼
Validate JSON
 │
 ▼
Calculate final importance
 │
 ▼
Cache result
 │
 ▼
Render TUI
```

---

# 9. Phase 1 — Fetch PR Metadata

Command:

```bash
gh pr view 1842 --json \
  number,title,body,commits,files,additions,deletions,baseRefName,headRefName,headRefOid
```

Python wrapper:

```python
def get_pr(repo: Path, number: int) -> PullRequest: ...
```

Requirements:

- detect whether current directory is a Git repository;
- verify `gh` exists;
- verify `gh auth status`;
- resolve PR number;
- retrieve head SHA;
- retrieve PR description;
- retrieve changed files.

Support later:

```bash
prlens
prlens 1842
prlens https://github.com/org/repo/pull/1842
```

---

# 10. Phase 2 — Fetch and Parse Diff

Use:

```bash
gh pr diff 1842 --patch
```

Parse unified diff into:

```text
ChangedFile
  └── DiffHunk
```

Do not depend on Codex to parse diffs.

Store:

- old/new line ranges;
- additions;
- deletions;
- file name;
- rename information;
- binary status;
- raw patch.

Libraries can be evaluated, but a small dedicated parser may be simpler because PRLens only needs a subset of unified diff semantics.

---

# 11. Phase 3 — Temporary Worktree

A raw diff is insufficient for understanding context.

Create a temporary worktree for the PR head:

```bash
git worktree add <temp-dir> <head-sha>
```

Example:

```text
~/.cache/prlens/worktrees/<repo>/<sha>/
```

The worktree lets the analyzer:

- inspect complete functions;
- inspect imports;
- search references;
- inspect neighboring types;
- inspect tests;
- let Codex reason over repository content.

Cleanup strategy:

- reuse worktrees by SHA;
- remove stale worktrees with a TTL;
- provide:

```bash
prlens cache clean
```

---

# 12. Phase 4 — Noise Classification

Before sending anything to Codex, identify low-value files.

Categories:

```text
BUSINESS_LOGIC
API
AUTH
DATA
CONFIG
UI
TEST
MIGRATION
GENERATED
SNAPSHOT
LOCKFILE
DOCUMENTATION
BUILD
CI
UNKNOWN
```

Initial heuristics:

## Generated

Patterns:

```text
generated/
gen/
*.generated.*
*_pb2.py
*.g.cs
openapi-client/
vendor/
```

Also inspect headers:

```text
DO NOT EDIT
generated by
auto-generated
```

## Lock files

Examples:

```text
package-lock.json
yarn.lock
pnpm-lock.yaml
poetry.lock
uv.lock
Cargo.lock
```

## Tests

Patterns:

```text
tests/
test_*.py
*_test.py
*.spec.ts
*.test.ts
```

## Migrations

Patterns:

```text
migrations/
alembic/
db/migrate/
```

The classifier should return probabilities rather than a single boolean.

---

# 13. Phase 5 — Static Importance Signals

Before asking Codex for a semantic score, calculate deterministic signals.

Example signals:

| Signal | Weight |
|---|---:|
| authorization code changed | +30 |
| exported/public behavior changed | +25 |
| DB write/query changed | +20 |
| API route changed | +20 |
| migration added | +15 |
| configuration default changed | +15 |
| widely referenced symbol changed | +15 |
| error handling changed | +10 |
| test-only change | -10 |
| snapshot | -20 |
| generated code | -30 |
| lock file | -40 |

These values should be configurable.

Example config:

```toml
[scoring]
auth_change = 30
api_change = 20
migration = 15

[noise]
generated = -30
lockfile = -40
snapshot = -20
```

---

# 14. Phase 6 — Changed Symbol Detection

The tool should identify functions, classes, methods, types, routes, and configuration keys touched by each hunk.

V1 support should focus on Python.

Use the built-in:

```python
ast
```

Strategy:

1. Parse the complete file from the PR worktree.
2. Build a map:

```text
line range -> symbol
```

Example:

```text
1-20   module
22-68  PermissionService
30-44  PermissionService.has_admin_access
46-61  PermissionService.can_delete_user
```

3. Map changed hunk lines to symbols.

This allows PRLens to say:

```text
Changed symbol:
PermissionService.can_delete_user
```

rather than only:

```text
src/auth/permissions.py:46-61
```

Later add:

- TypeScript;
- JavaScript;
- Go;
- Rust;
- Java.

Tree-sitter is a good future direction.

---

# 15. Phase 7 — Reference Search

For each important changed symbol:

```bash
rg "can_delete_user"
```

Collect likely references.

Classify references into:

```text
caller
import
test
route
worker
configuration
unknown
```

V1 does not need a perfect call graph.

The goal is to provide evidence about potential blast radius.

Example:

```text
PermissionService.can_delete_user
├── UsersController.delete
├── BulkDeleteUsersJob
├── AdminUserService.remove
└── tests/test_user_permissions.py
```

Limit search results to avoid overwhelming Codex.

---

# 16. Phase 8 — Build Codex Context

Do not send the entire repository.

Build a compact analysis bundle.

Example:

```text
PR TITLE
Add organization-level administration

PR DESCRIPTION
...

FILES
...

STATIC SIGNALS
...

CHANGE HUNK 1
...

CONTAINING SYMBOL
...

REFERENCES
...

NEIGHBORING CODE
...
```

Include:

- PR intent;
- changed hunks;
- containing symbols;
- static scores;
- nearby code;
- selected reference snippets;
- tests;
- file category.

Avoid:

- lockfile contents;
- entire generated files;
- full repository dumps.

---

# 17. Phase 9 — Codex Semantic Analysis

Use:

```bash
codex exec
```

The key requirement is structured output.

Example:

```bash
codex exec \
  --output-schema schemas/codex_analysis.schema.json \
  "<analysis prompt>"
```

The model should be responsible for:

1. grouping hunks into logical changes;
2. describing before/after behavior;
3. explaining why the change exists;
4. estimating business impact;
5. estimating behavioral significance;
6. identifying likely affected areas;
7. identifying review questions;
8. detecting suspicious omissions;
9. estimating expectedness;
10. estimating confidence.

The model should **not** be solely responsible for the final importance score.

---

# 18. Codex Output Schema

Example:

```json
{
  "pr_intent": "Allow organization administrators to manage users.",
  "changes": [
    {
      "id": "C1",
      "title": "Organization admins gain delete permission",

      "business_impact": 9,
      "behavior_change": 10,
      "blast_radius": 8,
      "security_sensitivity": 9,
      "data_sensitivity": 3,
      "novelty": 7,

      "confidence": 0.94,
      "unexpectedness": 0.21,

      "risk": "high",

      "before": "Only project administrators can delete users.",
      "after": "Organization administrators can also delete users.",

      "why": "The PR introduces organization-wide administrative privileges.",

      "business_effect": "Organization administrators can manage users across projects.",

      "files": [
        "src/auth/permissions.py",
        "src/services/users.py"
      ],

      "hunk_ids": [
        "H3",
        "H7"
      ],

      "affected_symbols": [
        "PermissionService.can_delete_user",
        "UserService.delete_user"
      ],

      "affected_components": [
        "DELETE /users/:id",
        "admin console",
        "bulk cleanup worker"
      ],

      "domains": [
        "authorization",
        "api"
      ],

      "tests": [
        "tests/test_permissions.py"
      ],

      "review_questions": [
        "Should organization admins be allowed to delete organization owners?"
      ],

      "possible_omissions": [
        "No audit logging change was found for the newly authorized path."
      ]
    }
  ]
}
```

Validate every response with Pydantic.

If validation fails:

1. retry once with schema error feedback;
2. if retry fails, retain static-only analysis;
3. never crash the UI.

---

# 19. Importance Scoring

Avoid asking the model for an arbitrary `0-100` score.

Instead calculate it from dimensions.

Example:

```python
semantic_score = (
    behavior_change * 0.25
    + business_impact * 0.20
    + blast_radius * 0.20
    + security_sensitivity * 0.15
    + data_sensitivity * 0.10
    + novelty * 0.10
)
```

Then combine with static signals:

```python
importance = normalize(semantic_score + static_signal_score - noise_penalty)
```

Suggested dimensions:

```text
behavior_change
business_impact
blast_radius
security_sensitivity
data_sensitivity
novelty
```

Each should be `0-10`.

---

# 20. Unexpectedness

Unexpectedness should be a separate metric.

Example:

```text
PR:
"Fix onboarding button copy"

Change:
Payment retry policy changed.

importance:      88
unexpectedness:  97
```

This should rank extremely highly.

Possible computation:

```text
unexpectedness =
    semantic distance from PR intent
    + unrelated subsystem change
    + weak justification
```

High importance + high unexpectedness should receive the highest attention.

Suggested sort key:

```python
review_priority = importance * 0.7 + unexpectedness * 0.3
```

Potentially boost:

```text
if importance > 70 and unexpectedness > 70:
    add critical review boost
```

---

# 21. Confidence

Every AI conclusion should include confidence.

Example:

```text
Importance: 94
Confidence: 55%
```

This communicates:

> This looks important, but the evidence is incomplete.

Low-confidence/high-importance items should remain near the top.

Do not suppress uncertain results.

---

# 22. Risk Classification

Suggested levels:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Potential CRITICAL domains:

```text
authentication
authorization
billing
payments
tenant isolation
data deletion
encryption
secrets
production infrastructure
schema destructive migration
```

The rule-based layer should be able to raise minimum risk.

Example:

```python
if category == "AUTHORIZATION":
    risk = max(risk, HIGH)
```

---

# 23. Blast Radius

V1 blast-radius calculation should combine:

```text
changed symbol
 │
 ├── direct textual references
 ├── imports
 ├── route references
 ├── workers
 ├── tests
 └── Codex inference
```

Output example:

```text
PermissionService.can_delete_user
│
├── UsersController.delete
│   └── DELETE /users/:id
│
├── BulkDeleteUsersJob
│
└── AdminUserService.remove
    └── Admin Console
```

Each relationship should carry an evidence type:

```text
STATIC_REFERENCE
IMPORT
ROUTE_MATCH
TEST_REFERENCE
CODEX_INFERENCE
```

This lets the UI distinguish known facts from inferred connections.

---

# 24. Before/After Behavior

This should be one of the most important UI elements.

Example:

```text
BEFORE
Only project admins could delete users.

AFTER
Organization admins can also delete users.
```

This is much easier to review than a generic explanation such as:

> Updated permission handling.

Codex should be explicitly prompted to describe observable behavior, not implementation mechanics.

---

# 25. Review Questions

The tool should generate questions, not only conclusions.

Example:

```text
Review questions

1. Should organization admins be able to delete organization owners?
2. Does this permission need to emit an audit event?
3. Should service accounts receive the same permission?
```

This makes the tool assist human review instead of replacing it.

---

# 26. Suspicious Omission Detection

Many AI-generated bugs come from code the agent did not modify.

Examples:

```text
Implementation changed but tests did not.
Permission changed but audit logs did not.
Enum gained a value but serializer did not.
Database model changed but migration is missing.
API changed but OpenAPI schema did not.
Retry behavior changed but metrics did not.
```

Codex should receive enough repository context to produce:

```json
{
  "possible_omissions": [
    "No migration was found for the newly added database field."
  ]
}
```

The deterministic layer can also check common patterns.

---

# 27. Review Budget Mode

A future high-value feature:

```bash
prlens 1842 --budget 5m
prlens 1842 --budget 15m
prlens 1842 --budget 30m
```

Map approximate review time to number and complexity of changes.

Example:

```text
5 minutes
Show top 3 important logical changes.

15 minutes
Show top 8.

30 minutes
Show all medium/high-impact changes.
```

A better later implementation can estimate review cost per logical change.

---

# 28. TUI Design

## Main screen

Three panes:

```text
┌──────────────────────┬───────────────────────────────────┬───────────────────────┐
│ CHANGES              │ DIFF                              │ CONTEXT               │
│                      │                                   │                       │
│ 96 Auth semantics    │ focused patch                     │ Before / After        │
│ 89 Delete endpoint   │                                   │ Why                   │
│ 76 Role fallback     │                                   │ Impact                │
│ 34 Migration         │                                   │ Risks                 │
│ 12 Tests             │                                   │ Questions             │
└──────────────────────┴───────────────────────────────────┴───────────────────────┘
```

## Keyboard shortcuts

Suggested:

```text
j / ↓       next change
k / ↑       previous change

enter       focus selected change
e           expand full file diff
c           collapse noise
a           show all changes
r           show review questions
i           show impact graph
t           show tests
o           show omissions
f           filter
/           search
q           quit
```

---

# 29. Change List Presentation

Example:

```text
96 🔴 AUTH   Organization admin permission
92 🔴 DATA   User deletion transaction changed
78 🟠 API    New fallback behavior
61 🟡 DATA   Migration adds organization_id
22 ⚪ TEST   Permission tests
 7 ⚪ GEN    OpenAPI client regeneration
```

Indicators:

```text
🔴 critical/high review priority
🟠 important
🟡 medium
⚪ low/noise
```

Optional markers:

```text
! unexpected
? low confidence
S security sensitive
D data sensitive
```

---

# 30. Context Panel

Suggested sections:

```text
OVERVIEW

Importance: 96
Risk: HIGH
Confidence: 94%
Unexpectedness: 21%

BEFORE

Only project administrators can delete users.

AFTER

Organization administrators can also delete users.

WHY

The PR introduces organization-wide administrator privileges.

AFFECTS

• DELETE /users/:id
• Admin console
• Bulk cleanup worker

REVIEW QUESTIONS

• Should organization admins delete owners?
• Should this action emit an audit event?

POSSIBLE OMISSIONS

• No audit logging update found.
```

---

# 31. Focused Diff

Only show the hunks associated with the selected logical change.

Example:

```diff
- if project.is_admin(user):
+ if project.is_admin(user) or organization.is_admin(user):
      delete_user()
```

Provide an option:

```text
[e] expand full file
```

The reviewer must always be able to inspect original code.

---

# 32. Caching

Codex analysis can be expensive.

Cache using:

```text
repository identity
+
base SHA
+
head SHA
+
analysis version
+
prompt version
```

Suggested location:

```text
~/.cache/prlens/
```

Structure:

```text
~/.cache/prlens/
├── analyses/
│   └── <repo>/<base>..<head>.json
└── worktrees/
    └── <repo>/<sha>/
```

Invalidate when:

- PR head SHA changes;
- analysis schema changes;
- prompt version changes;
- scoring version changes.

---

# 33. Incremental Reanalysis

Important future optimization.

If a PR receives another commit:

```text
previous head: abc123
new head:      def456
```

Do not necessarily reanalyze everything.

Instead:

1. calculate delta;
2. detect affected logical changes;
3. re-run static signals on changed files;
4. re-run Codex only for affected groups.

This can make the tool suitable for active PRs.

---

# 34. Configuration

Repository-local config:

```text
.prlens.toml
```

Example:

```toml
[paths]
generated = [
  "src/generated/**",
  "clients/openapi/**"
]

high_impact = [
  "src/auth/**",
  "src/billing/**",
  "src/payments/**"
]

low_impact = [
  "docs/**"
]

[domains]
"src/auth/**" = "AUTH"
"src/billing/**" = "BILLING"
"src/api/**" = "API"

[scoring]
auth_change = 30
migration = 15
generated_penalty = 30

[codex]
enabled = true
```

Later allow repository-specific review instructions:

```toml
[review]
invariants = [
  "All cross-tenant database access must enforce tenant_id.",
  "Destructive user actions must emit an audit event.",
  "Billing operations must be idempotent."
]
```

These invariants can become extremely valuable for AI-heavy repositories.

---

# 35. Repository Invariants

This should become a major feature after V1.

Example configuration:

```text
- All endpoints require authentication unless explicitly marked public.
- Tenant data must never cross tenant boundaries.
- User deletion must emit an audit event.
- Payment retries must be idempotent.
```

Codex can evaluate important changes against these rules.

Output:

```text
INVARIANT WARNING

"User deletion must emit an audit event."

The newly authorized organization-admin deletion path does not
appear to introduce additional audit handling.

Confidence: 71%
```

---

# 36. CLI Commands

V1:

```bash
prlens <pr-number>
```

Recommended eventual commands:

```bash
prlens 1842
prlens .
prlens analyze 1842
prlens show 1842
prlens cache clean
prlens config init
prlens doctor
```

## `prlens doctor`

Check:

```text
✓ git installed
✓ gh installed
✓ GitHub authenticated
✓ codex installed
✓ current directory is repository
✓ ripgrep installed
```

---

# 37. Error Handling

The tool should degrade gracefully.

## Codex unavailable

Still show:

- diff;
- file classification;
- static importance;
- changed symbols;
- references.

Display:

```text
Semantic analysis unavailable.
Showing static review priority only.
```

## `gh` unavailable

Fail early with actionable instructions.

## Invalid Codex JSON

Retry once.

If still invalid:

- log raw output;
- continue with static analysis.

## Binary files

Show metadata only.

---

# 38. Security

Because Codex will inspect source code, the tool should clearly expose when AI analysis is enabled.

Support:

```bash
prlens 1842 --no-ai
```

Repository config:

```toml
[codex]
enabled = false
```

Never send:

- `.env`;
- secrets;
- ignored files;
- arbitrary files unrelated to analysis.

Respect `.gitignore`.

Potential later feature:

```text
.aiignore
.prlensignore
```

---

# 39. Logging and Debugging

Support:

```bash
prlens 1842 --debug
```

Log:

```text
~/.cache/prlens/logs/
```

Useful diagnostics:

- `gh` command;
- worktree;
- parsed hunk count;
- ignored files;
- static scores;
- Codex execution metadata;
- schema validation failures;
- cache hits.

Do not log secret file contents.

---

# 40. Testing Strategy

## Unit tests

Test:

- diff parser;
- file classifier;
- scoring;
- symbol mapping;
- cache keys;
- JSON schema validation;
- ranking.

## Fixture repositories

Create tiny repositories with known changes.

Example fixtures:

```text
auth_change/
generated_noise/
migration/
api_change/
missing_test/
unrelated_change/
```

Each fixture should define expected:

```text
important files
noise files
changed symbols
ranking
```

## Codex tests

Do not require live Codex for normal unit tests.

Use saved JSON responses.

Separate optional integration tests:

```bash
pytest -m codex
```

---

# 41. Evaluation Dataset

Before tuning importance scoring, create a small dataset of real PRs.

For each PR manually label:

```text
top important changes
low-value changes
unexpected changes
business-impact files
security-sensitive changes
```

Then evaluate:

```text
Did PRLens place the reviewer-important changes near the top?
```

Metrics:

```text
Top-3 recall
Top-5 recall
Noise reduction
Logical-change grouping quality
```

The most important metric is probably:

> What percentage of human-important changes appear in the top 5 items?

---

# 42. Performance Targets

Initial targets:

```text
PR < 100 changed files:
static analysis < 3 seconds

TUI startup with cached analysis:
< 1 second

Cold semantic analysis:
dominated by Codex execution
```

The UI should open early if possible and display:

```text
Analyzing semantic changes...
```

Static results can be displayed while Codex analysis completes if architecture permits.

---

# 43. Implementation Milestones

## Milestone 0 — Project skeleton

Deliverables:

- Python package;
- `pyproject.toml`;
- Typer CLI;
- dependency checks;
- basic configuration;
- test setup.

Command:

```bash
prlens --help
```

---

## Milestone 1 — GitHub PR ingestion

Deliverables:

- detect repository;
- fetch PR metadata;
- fetch PR diff;
- parse files;
- parse hunks.

Command:

```bash
prlens analyze 1842 --json
```

Output:

```json
{
  "files": [...],
  "hunks": [...]
}
```

---

## Milestone 2 — Noise filtering

Deliverables:

- generated-file detection;
- test detection;
- lockfile detection;
- migration detection;
- simple file classification.

Output:

```text
AUTH        src/auth/permissions.py
TEST        tests/test_permissions.py
GENERATED   clients/generated.ts
LOCKFILE    pnpm-lock.yaml
```

---

## Milestone 3 — Static scoring

Deliverables:

- weighted deterministic signals;
- ranking;
- configurable scoring.

Command:

```bash
prlens analyze 1842 --static
```

Output:

```text
92 src/auth/permissions.py
64 src/api/users.py
21 tests/test_users.py
 4 generated/client.ts
```

---

## Milestone 4 — Worktree and symbol extraction

Deliverables:

- create/reuse worktree;
- Python AST support;
- map hunks to symbols;
- surrounding source extraction.

Example:

```text
src/auth/permissions.py:46-61
→ PermissionService.can_delete_user
```

---

## Milestone 5 — Reference discovery

Deliverables:

- ripgrep integration;
- reference ranking;
- test-reference detection;
- route/reference hints.

Example:

```text
PermissionService.can_delete_user
├── UsersController.delete
├── AdminUserService.remove
└── tests/test_permissions.py
```

---

## Milestone 6 — Codex integration

Deliverables:

- `codex exec` wrapper;
- structured output schema;
- prompts;
- Pydantic validation;
- retry/error handling;
- cache.

Output:

```json
{
  "changes": [...]
}
```

---

## Milestone 7 — Logical change grouping

Deliverables:

- Codex groups hunks;
- stable hunk IDs;
- logical changes reference hunks;
- before/after behavior;
- reason;
- review questions.

This milestone proves the primary product hypothesis.

---

## Milestone 8 — Final scoring

Deliverables:

- combine static and semantic signals;
- importance;
- risk;
- confidence;
- unexpectedness;
- review priority sorting.

---

## Milestone 9 — Basic TUI

Deliverables:

- change list;
- diff view;
- context panel;
- keyboard navigation;
- loading/error states.

This is the first usable release.

Suggested version:

```text
v0.1.0
```

---

## Milestone 10 — Impact view

Deliverables:

- symbol references;
- affected components;
- evidence types;
- tree visualization.

Suggested version:

```text
v0.2.0
```

---

## Milestone 11 — Omission detection

Deliverables:

- tests missing;
- migration mismatch;
- audit mismatch;
- common repository conventions;
- Codex omission reasoning.

Suggested version:

```text
v0.3.0
```

---

## Milestone 12 — Repository invariants

Deliverables:

- `.prlens.toml`;
- custom invariants;
- invariant warnings;
- repository-specific scoring.

Suggested version:

```text
v0.4.0
```

---

# 44. Recommended V1 Scope

V1 should implement only:

```text
1. Fetch PR metadata with gh
2. Fetch and parse diff
3. Create temporary worktree
4. Classify obvious noise
5. Calculate static importance
6. Extract changed Python symbols
7. Search references using ripgrep
8. Run Codex semantic analysis
9. Group hunks into logical changes
10. Calculate final priority
11. Show ordered changes in Textual
12. Show focused diff
13. Show context / before / after / risk / questions
14. Expand to full file diff
```

Do not add more until this workflow feels genuinely useful.

---

# 45. Suggested First Release Acceptance Criteria

The first release is successful when a reviewer can run:

```bash
prlens 1842
```

against a large AI-generated PR and within the first screen understand:

1. the top 3–7 meaningful changes;
2. which changes alter business behavior;
3. which change is most risky;
4. which change is unexpected;
5. which files implement each logical change;
6. the before/after semantics;
7. what other code paths may be affected;
8. which questions deserve human review.

The reviewer must also be able to reach the original full diff without leaving the application.

---

# 46. Potential Future Features

After validating V1:

## GitHub review integration

Allow:

```text
comment
approve
request changes
```

through `gh`.

## PR queue mode

```bash
prlens
```

Show open PRs ordered by:

```text
review risk
size
age
author
```

## Review budget

```bash
prlens 1842 --budget 10m
```

## Change history

Show when important code was introduced and how often it changes.

## Cross-PR analysis

Identify:

```text
This permission logic changed in 4 PRs this month.
```

## Agent attribution

If commits identify different AI agents:

```text
Logical change C3 primarily came from agent commit abc123.
```

## IDE integration

Open the selected logical change in:

```text
VS Code
Cursor
JetBrains
```

## ghui integration

Potential later paths:

1. launch PRLens from ghui;
2. expose PRLens analysis as JSON;
3. add PRLens semantic panel to ghui;
4. eventually port the analyzer contract into a native ghui extension.

Keep the analysis engine independent from the UI so this remains possible.

---

# 47. Internal API Boundaries

Keep these layers separate:

```text
GitHub Adapter
    ↓
Diff Model
    ↓
Static Analysis
    ↓
Semantic Analysis
    ↓
Scoring
    ↓
Presentation
```

The TUI should never directly call Codex.

The Codex layer should never directly render UI.

The scoring layer should operate entirely on typed models.

This separation will make it easier to add:

```text
JSON output
HTML reports
GitHub comments
ghui integration
IDE integration
```

later.

---

# 48. Proposed Core Interfaces

```python
class PRProvider(Protocol):
    def get_pr(self, number: int) -> PullRequest: ...
    def get_diff(self, number: int) -> str: ...


class StaticAnalyzer(Protocol):
    def analyze(
        self,
        pr: PullRequest,
        repo: Path,
    ) -> StaticAnalysisResult: ...


class SemanticAnalyzer(Protocol):
    def analyze(
        self,
        context: AnalysisContext,
    ) -> SemanticAnalysisResult: ...


class ChangeScorer(Protocol):
    def score(
        self,
        change: LogicalChange,
        static: StaticSignals,
    ) -> float: ...
```

This also makes testing much easier.

---

# 49. First Development Tasks

Recommended first tickets:

```text
PL-001 Initialize Python project
PL-002 Add Typer CLI
PL-003 Add dependency doctor command
PL-004 Add gh subprocess wrapper
PL-005 Fetch PR metadata
PL-006 Fetch unified diff
PL-007 Implement diff parser
PL-008 Add changed-file models
PL-009 Add file classifier
PL-010 Add static importance scorer
PL-011 Add worktree manager
PL-012 Add Python AST symbol mapping
PL-013 Add ripgrep reference search
PL-014 Define Codex JSON schema
PL-015 Implement Codex client
PL-016 Implement semantic analysis prompt
PL-017 Validate Codex responses
PL-018 Group hunks into logical changes
PL-019 Combine semantic + static ranking
PL-020 Add Textual application
PL-021 Add change-list pane
PL-022 Add focused diff pane
PL-023 Add context pane
PL-024 Add full-diff expansion
PL-025 Add cache
PL-026 Add integration fixture PR
```

---

# 50. Critical Product Decisions to Validate Early

Before investing heavily, validate these assumptions:

## Assumption 1

Logical-change grouping is more useful than file-level summaries.

## Assumption 2

Reviewers trust a ranked list if the ranking explains itself.

## Assumption 3

Before/after behavior is more valuable than generic AI summaries.

## Assumption 4

Static signals + AI reasoning produce better importance ranking than AI scores alone.

## Assumption 5

Unexpectedness is a useful independent review dimension.

## Assumption 6

Review questions create more value than AI conclusions.

## Assumption 7

A lightweight blast-radius approximation is useful even when it is not a perfect call graph.

These should guide early user testing.

---

# 51. Product Philosophy

PRLens should not tell the reviewer:

> This PR is safe.

It should tell the reviewer:

```text
These 5 changes appear to contain most of the behavioral decisions.

Two touch authorization.

One appears unrelated to the PR intent.

One changes a widely used data path.

Here is what changed before/after.

Here are the questions worth answering.

Here is the exact code.
```

The purpose of the tool is to focus human attention.

That is especially important for AI-generated code, where code generation becomes cheap but human understanding remains expensive.

---

# 52. Short V1 Architecture Summary

```text
                    GitHub PR
                       │
                       ▼
                     gh CLI
                       │
                       ▼
                  Diff Parser
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
      Noise Classifier      Git Worktree
             │                   │
             ▼                   ▼
      Static Scoring      Symbol Extraction
             │                   │
             └─────────┬─────────┘
                       ▼
               Reference Search
                       │
                       ▼
                Analysis Context
                       │
                       ▼
                   Codex CLI
                       │
                structured JSON
                       │
                       ▼
                 Change Grouper
                       │
                       ▼
                 Final Scoring
                       │
                       ▼
                   Textual TUI
```

---

# 53. Definition of Done for V1

V1 is done when:

- `prlens <pr-number>` works in a GitHub repository;
- large diffs are parsed reliably;
- obvious noise is deprioritized;
- Python changed symbols are identified;
- references are collected;
- Codex returns validated structured analysis;
- related hunks are grouped into logical changes;
- logical changes are ranked;
- each important change has:
  - before;
  - after;
  - why;
  - risk;
  - affected areas;
  - review questions;
- the TUI supports keyboard navigation;
- focused diffs are visible;
- the full original diff is always accessible;
- results are cached by PR SHA;
- failure of AI analysis does not make the application unusable.

At that point, use the tool on real AI-heavy PRs before adding further features.
