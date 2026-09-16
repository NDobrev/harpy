# ADR 0017 — Browser workspace and hosted tenancy

## Status

Accepted for implementation; the browser/server implementation is not yet delivered.

Supersedes the terminal-only/no-backend-server product decision in the review-workspace design and the no-server-database restriction in ADR 0012. The no-automatic-cloud-synchronization decision remains in force. Existing source-snapshot, explicit-analysis, analyzer-role, scoring, and layer invariants remain in force.

## Context

Harpy users need a browser interface with current TUI feature parity, full mobile workflows, and White, Black, and Dark Blue themes combining neumorphic surfaces with restrained neon accents. The product must support local use, self-hosted teams, and a pooled multi-tenant SaaS pilot.

The chosen collaboration model has shared decisions and notes. Users retain individual GitHub inboxes and personal preferences/navigation. Hosted identity comes from existing SSO; operators provision credentials. SaaS onboarding is managed, without public signup or billing in the first release.

The current active JSON storage/catalog, whole-session TUI writes, synchronous service execution, in-memory job tracking, and mutable report lookup are insufficient for those guarantees. Adding an HTTP wrapper alone would permit lost edits, incoherent historical evidence, and unsafe sharing of credentials/state.

## Decision

- Add React/TypeScript/Vite presentation and a FastAPI transport over a tenant-aware application service. Retain TUI/CLI compatibility; web transport follows equivalent layer boundaries and never invokes provider/storage implementations directly.
- Add transactional repositories and migrations: SQLite for local web/shared local TUI state and PostgreSQL for hosted modes. Import legacy state with backups and preserve human work. Unmigrated TUI-only installations may retain the existing fallback when SQLite is unavailable.
- Persist immutable reports and snapshot-bound artifacts independently of mutable browser/latest-report indexes. New reports start unreviewed; historical decisions and notes remain inspectable.
- Separate versioned shared decisions/notes from personal navigation, preferences, and inboxes. Use optimistic concurrency, explicit conflict resolution, and append-only attributed edit history.
- Use durable jobs, leases, cancellation propagation, provider-invocation records, and reconnectable server-sent events. Never silently repeat a provider call whose completion is indeterminate.
- Support pooled SaaS with mandatory tenant context, repository grants, PostgreSQL row-level security, tenant-separated artifacts/caches, and isolated hosted job containers. No credential fallback to the operator's home directory.
- Use loopback bootstrap authentication locally and a trusted, validated OIDC gateway for hosted access. Provision memberships, repositories, grants, and secrets through operator tools.
- Ship one browser application across deployment modes, with bundled assets for local installation and a Compose distribution for hosted use. Local and hosted databases do not automatically synchronize.
- Make desktop, tablet, phone, accessibility, and all three themes release requirements. Keep the logical change and original evidence central to every layout.

## Consequences

The implementation is a product expansion with storage, identity, execution, and operations work, not merely a new renderer. The current model default and read-only analyzer contract do not change. Verification execution, GitHub submission, and other backend-only features remain outside initial web parity.

Local web requires Python SQLite support. Hosted deployments require PostgreSQL, SSO, provisioned credentials, an isolated worker runtime, and operator-managed backups. The initial SaaS can pool tenants on one host; multi-host artifact storage and high availability are not claimed by this decision.

New tests must enforce browser/service layering, local TUI/web compatibility, transactional conflicts, report immutability, per-user credentials, and tenant isolation across data, artifacts, jobs, and events. Existing tests must not be weakened. `make check` remains the acceptance command and must stay free of internet/live-provider requirements.

The complete implementation and acceptance contract is the [Harpy Web implementation PRD](../design/web-review-workspace-prd.md).
