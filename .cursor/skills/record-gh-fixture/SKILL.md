---
name: record-gh-fixture
description: Record a live gh pr view/diff into tests/fixtures/gh for offline replay.
---

# Record a gh fixture

Only sanctioned live `gh` capture for tests.

1. From a real clone: `gh pr view <n> --json number,title,body,commits,files,additions,deletions,baseRefName,headRefName,headRefOid > tests/fixtures/gh/<name>.view.json`
2. `gh pr diff <n> --patch > tests/fixtures/gh/<name>.diff`
3. Redact tokens, emails, and secrets before committing.
4. Point `tests/fake_bin/gh` at the new files via `HARPY_GH_FIXTURE=<name>`.
5. Add a unit test that uses the fixture. Do not call live `gh` from that test.
