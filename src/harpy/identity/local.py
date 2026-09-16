"""Loopback bootstrap and process-local sessions."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from harpy.identity.csrf import issue_csrf_token, require_csrf, require_same_origin
from harpy.identity.types import AuthenticationError, LocalSession, Principal

BOOTSTRAP_TTL = timedelta(minutes=5)
SESSION_TTL = timedelta(hours=12)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


def bootstrap_url(public_origin: str, token: str) -> str:
    origin = public_origin.rstrip("/")
    if "?" in origin or "#" in origin:
        raise AuthenticationError("bootstrap origin must not include query or fragment")
    return f"{origin}/#bootstrap={token}"


def validate_loopback_host(host: str, *, port: int) -> None:
    name = host.strip().lower()
    if ":" in name:
        name, raw_port = name.rsplit(":", 1)
        if raw_port != str(port):
            raise AuthenticationError("host mismatch")
    if name not in LOOPBACK_HOSTS:
        raise AuthenticationError("host mismatch")


@dataclass
class _Pending:
    digest: str
    expires_at: datetime
    consumed: bool = False


class LocalAuthenticator:
    def __init__(
        self,
        *,
        public_origin: str,
        port: int,
        principal: Principal,
        clock: Clock | None = None,
    ) -> None:
        self.public_origin = public_origin.rstrip("/")
        self.port = port
        self.principal = principal
        self._clock = clock or utcnow
        self._pending: dict[str, _Pending] = {}
        self._sessions: dict[str, LocalSession] = {}

    def issue_bootstrap(self) -> str:
        token = secrets.token_hex(32)
        digest = sha256(token.encode()).hexdigest()
        self._pending[digest] = _Pending(digest=digest, expires_at=self._clock() + BOOTSTRAP_TTL)
        return bootstrap_url(self.public_origin, token)

    def exchange(
        self,
        token: str,
        *,
        host: str,
        origin: str,
        query: Mapping[str, str] | None = None,
    ) -> LocalSession:
        if query:
            raise AuthenticationError("bootstrap token must not be a query parameter")
        validate_loopback_host(host, port=self.port)
        require_same_origin(origin=origin, public_origin=self.public_origin)
        digest = sha256(token.encode()).hexdigest()
        pending = self._pending.get(digest)
        now = self._clock()
        if pending is None or pending.consumed or pending.expires_at <= now:
            raise AuthenticationError("bootstrap token invalid")
        pending.consumed = True
        session = LocalSession(
            session_id=str(uuid4()),
            csrf_token=issue_csrf_token(),
            expires_at=now + SESSION_TTL,
            principal=self.principal,
        )
        self._sessions[session.session_id] = session
        return session

    def resolve(self, session_id: str) -> LocalSession:
        session = self._sessions.get(session_id)
        if session is None or session.expires_at <= self._clock():
            raise AuthenticationError("session expired")
        return session

    def logout(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def authorize_unsafe(
        self,
        session_id: str,
        *,
        method: str,
        host: str,
        origin: str,
        headers: Mapping[str, str],
    ) -> LocalSession:
        validate_loopback_host(host, port=self.port)
        session = self.resolve(session_id)
        require_csrf(
            method=method,
            headers=headers,
            origin=origin,
            public_origin=self.public_origin,
            expected_token=session.csrf_token,
        )
        return session


def implicit_principal(*, user_id: UUID | None = None) -> Principal:
    return Principal(
        user_id=user_id or uuid4(),
        issuer="local",
        subject="implicit",
        display_name="Local reviewer",
    )
