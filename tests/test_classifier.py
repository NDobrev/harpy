from __future__ import annotations

from harpy.analysis.file_classifier import classify_path, primary_category
from harpy.models import FileCategory


def test_lockfile_and_generated() -> None:
    lock = classify_path("pnpm-lock.yaml")
    assert lock[FileCategory.LOCKFILE] == 1.0
    gen = classify_path("src/generated/client.ts")
    assert gen[FileCategory.GENERATED] >= 0.8
    header = classify_path("src/foo.py", header="# AUTO-GENERATED. DO NOT EDIT.")
    assert header[FileCategory.GENERATED] >= 0.9


def test_auth_and_test() -> None:
    auth = classify_path("src/auth/permissions.py")
    assert primary_category(auth) is FileCategory.AUTH
    test = classify_path("tests/test_permissions.py")
    assert primary_category(test) is FileCategory.TEST
