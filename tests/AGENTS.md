# Tests

- No network. No live `cursor-agent` unless `@pytest.mark.cursor`.
- Prefer fixtures (`tests/fixtures/`, `tests/fake_bin/gh`) over mocks.
- Goldens via syrupy. Update only with `make goldens` when the change is intentional.
- Never edit or delete an existing test to make a change pass.
- `tests/test_architecture.py` is load-bearing. Do not weaken it.
