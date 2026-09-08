# Evaluation

Default checks use locally stored, sanitized fixtures. Live agent, network, and Docker
evaluations stay outside `make check`.

## Quality gates before V2 default

- Diff inventory is fully accounted for, including explicit exclusions.
- Displayed citations pass source-location validation.
- Unavailable scopes have an explicit state.
- Reviewed state does not carry across changed evidence.
- Important-change recall is measured against the labeled baseline once the
  20-case corpus lands.

## Corpus (HP-068)

Ten agent-produced changes and ten contributor-style changes, covering Python,
TypeScript/TSX, Go, Rust, and SQL, plus multi-revision sequences. Store fixtures
under `tests/fixtures/eval/` as they are labeled.
