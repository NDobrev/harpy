# ADR 0016 — GitHub CI and releases

## Status

Accepted; supersedes ADR 0003.

## Context

Harpy now has a GitHub remote. The repository needs an enforced pull-request
gate and a reproducible way to publish installable artifacts without taking on
a package-index release process.

## Decision

- Changes to `main` go through pull requests and the `check` status must pass.
  Review approval is not required. Force-pushes and branch deletion are blocked.
- `make check` remains the local and CI acceptance command. It validates the
  lockfile, formatting, lint, types, offline tests, and package construction.
- Dependabot proposes weekly grouped updates for uv and GitHub Actions.
- `pyproject.toml` is the package version source. `harpy.__version__` reads the
  installed distribution metadata.
- A maintainer creates a release by dispatching the release workflow from
  `main` with the version already merged by a pull request.
- Release tags are `v<PEP 440 version>`. Stable versions use `X.Y.Z`;
  prereleases use forms such as `X.Y.Zrc1`.
- Releases are GitHub Releases only. Each release contains one wheel and one
  source archive, generated release notes, and GitHub artifact provenance.
- Ordinary CI has read-only repository access. Write and OIDC permissions are
  scoped to the release job.
- Published tags and releases are immutable. Corrections use a new version.

## Consequences

- Contributors can run the same gate locally that GitHub requires.
- A version bump is reviewed before a release can be dispatched.
- Users install from a GitHub Release rather than PyPI.
- `git`, authenticated `gh`, and optional `cursor-agent` remain external
  runtime prerequisites and are not bundled in the wheel.
- Release automation cannot bypass a failing acceptance gate.
