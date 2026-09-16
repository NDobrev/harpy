"""Identity value types. No persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class IdentityError(RuntimeError):
    pass


class AuthenticationError(IdentityError):
    pass


class AccessDenied(IdentityError):
    def __init__(self, message: str = "not found") -> None:
        super().__init__(message)


class NotFound(IdentityError):
    def __init__(self, message: str = "not found") -> None:
        super().__init__(message)


class AccessRevoked(IdentityError):
    def __init__(self) -> None:
        super().__init__("access revoked")


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    issuer: str
    subject: str
    display_name: str


@dataclass(frozen=True)
class TenantMembership:
    tenant_id: UUID
    slug: str
    name: str
    role: str
    state: str
    authorization_version: int


@dataclass(frozen=True)
class AccessContext:
    tenant_id: UUID
    actor_id: UUID
    role: str
    correlation_id: UUID
    authenticated_subject: str
    authorization_version: int


@dataclass(frozen=True)
class LocalSession:
    session_id: str
    csrf_token: str
    expires_at: datetime
    principal: Principal


HIDDEN = "not found"
