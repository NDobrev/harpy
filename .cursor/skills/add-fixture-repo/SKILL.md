---
name: add-fixture-repo
description: Add a tiny fixture git repo under tests/fixtures/repos with expected ranking labels.
---

# Add a fixture repo

1. Create `tests/fixtures/repos/<name>/` as a real git repo (`git init`, one or two commits).
2. Include `expected.toml` with `important_files`, `noise_files`, `changed_symbols`, `ranking`.
3. Drive creation from `scripts/build_fixture_repos.py` so the fixture is reproducible.
4. Add a test under `tests/test_fixtures.py` that asserts ranking against `expected.toml`.
5. Run `make check`. Do not hit the network.
