---
name: record-cursor-fixture
description: Record a live cursor-agent ask-mode JSON transcript into tests/fixtures/cursor. Only sanctioned live agent calls for tests.
---

# Record a cursor-agent fixture

This is the only sanctioned live `cursor-agent` call for tests.

```bash
printf '%s' "$PROMPT" | cursor-agent -p --output-format json --mode ask --trust \
  --model cursor-grok-4.6-high-fast --workspace <dir> \
  > tests/fixtures/cursor/<name>.json
```

Record stderr separately if the process fails (docs: no well-formed JSON on failure).

Redact workspace paths that are machine-specific if they leak secrets. Do not commit `.env` contents.

Mark any test that re-runs the live command `@pytest.mark.cursor`. Default tests must replay the saved JSON.
