#!/usr/bin/env python3
"""Write tiny fixture trees used by tests/test_fixtures.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "repos"

TREES: dict[str, dict[str, str]] = {
    "auth_change": {
        "src/auth/permissions.py": "def can_delete_user(user):\n    return user.is_org_admin\n",
        "tests/test_permissions.py": "def test_ok():\n    assert True\n",
        "expected.toml": 'important_files = ["src/auth/permissions.py"]\nnoise_files = []\nchanged_symbols = ["can_delete_user"]\nranking = ["src/auth/permissions.py", "tests/test_permissions.py"]\n',
    },
    "generated_noise": {
        "src/generated/client.ts": "/* AUTO-GENERATED. DO NOT EDIT. */\nexport const x = 1;\n",
        "src/app.py": "def main():\n    return 1\n",
        "expected.toml": 'important_files = ["src/app.py"]\nnoise_files = ["src/generated/client.ts"]\nchanged_symbols = ["main"]\nranking = ["src/app.py", "src/generated/client.ts"]\n',
    },
    "migration": {
        "alembic/versions/0001_add_org.py": 'def upgrade():\n    """add org"""\n    pass\n',
        "src/models/user.py": "class User:\n    organization_id = None\n",
        "expected.toml": 'important_files = ["alembic/versions/0001_add_org.py", "src/models/user.py"]\nnoise_files = []\nchanged_symbols = ["User"]\nranking = ["src/models/user.py", "alembic/versions/0001_add_org.py"]\n',
    },
    "api_change": {
        "src/api/users.py": "@router.delete('/users/{id}')\ndef delete_user(id):\n    return id\n",
        "expected.toml": 'important_files = ["src/api/users.py"]\nnoise_files = []\nchanged_symbols = ["delete_user"]\nranking = ["src/api/users.py"]\n',
    },
    "missing_test": {
        "src/billing/charge.py": "def charge(amount):\n    return amount\n",
        "expected.toml": 'important_files = ["src/billing/charge.py"]\nnoise_files = []\nchanged_symbols = ["charge"]\nranking = ["src/billing/charge.py"]\n',
    },
    "unrelated_change": {
        "docs/copy.md": "Fix onboarding button copy\n",
        "src/payments/retry.py": "def retry_policy():\n    return 7\n",
        "expected.toml": 'important_files = ["src/payments/retry.py"]\nnoise_files = ["docs/copy.md"]\nchanged_symbols = ["retry_policy"]\nranking = ["src/payments/retry.py", "docs/copy.md"]\n',
    },
}


def main() -> None:
    for name, files in TREES.items():
        base = ROOT / name
        for rel, content in files.items():
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    print(f"wrote {len(TREES)} fixture repos under {ROOT}")


if __name__ == "__main__":
    main()
