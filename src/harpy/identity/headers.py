"""Ignore client-supplied identity headers."""

from __future__ import annotations

from collections.abc import Mapping

SPOOFED_IDENTITY_HEADERS = frozenset(
    {
        "x-forwarded-user",
        "x-forwarded-email",
        "x-auth-request-user",
        "x-auth-request-email",
        "x-remote-user",
        "x-tenant-id",
    }
)


def request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SPOOFED_IDENTITY_HEADERS:
            continue
        cleaned[key] = value
    return cleaned


def authorization_bearer(headers: Mapping[str, str]) -> str | None:
    raw = headers.get("authorization") or headers.get("Authorization")
    if raw is None or not raw.startswith("Bearer "):
        return None
    token = raw.removeprefix("Bearer ").strip()
    return token or None
