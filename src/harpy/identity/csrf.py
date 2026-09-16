"""Session-bound CSRF tokens for unsafe methods."""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Mapping
from hashlib import sha256

from harpy.identity.types import AuthenticationError

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def issue_csrf_token() -> str:
    return secrets.token_hex(32)


def csrf_binding(session_id: str, token: str, secret: bytes) -> str:
    return hmac.new(secret, f"{session_id}:{token}".encode(), sha256).hexdigest()


def require_same_origin(*, origin: str, public_origin: str) -> None:
    if origin.rstrip("/") != public_origin.rstrip("/"):
        raise AuthenticationError("origin mismatch")


def require_csrf(
    *,
    method: str,
    headers: Mapping[str, str],
    origin: str,
    public_origin: str,
    expected_token: str,
) -> None:
    require_same_origin(origin=origin, public_origin=public_origin)
    if method.upper() not in UNSAFE_METHODS:
        return
    offered = headers.get("x-csrf-token") or headers.get("X-CSRF-Token") or ""
    if not offered or not hmac.compare_digest(offered, expected_token):
        raise AuthenticationError("csrf mismatch")
