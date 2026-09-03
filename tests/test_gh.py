from __future__ import annotations

from pathlib import Path

from harpy.github.gh import GhProvider, resolve_pr_ref


def test_resolve_pr_ref() -> None:
    assert resolve_pr_ref("1842") == (None, 1842)
    assert resolve_pr_ref(".") == (None, None)
    repo, number = resolve_pr_ref("https://github.com/org/repo/pull/12")
    assert repo == "org/repo"
    assert number == 12


def test_fake_gh(fake_gh_path: Path) -> None:
    provider = GhProvider()
    pr = provider.get_pr(1842)
    assert pr.number == 1842
    assert pr.title
    assert pr.head_sha
    diff = provider.get_diff(1842)
    assert "diff --git" in diff
