"""Tenant identity directory, authorization, and operator provisioning."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from harpy.identity.access import Action, allows
from harpy.identity.types import (
    HIDDEN,
    AccessContext,
    AccessDenied,
    AccessRevoked,
    NotFound,
    Principal,
    TenantMembership,
)
from harpy.storage.schema import (
    AdminAudit,
    Credential,
    Job,
    Membership,
    Repository,
    RepositoryGrant,
    Review,
    Tenant,
    User,
    utcnow,
)
from harpy.storage.secrets import (
    KeyRing,
    associated_data,
    decrypt_secret,
    encrypt_secret,
)
from harpy.storage.workspace import ActorContext, TenantWorkspace


class AccessDirectory:
    def __init__(self, session: Session) -> None:
        self.session = session

    def principal_for(self, issuer: str, subject: str) -> Principal | None:
        user = self.session.scalar(
            select(User).where(User.issuer == issuer, User.subject == subject)
        )
        if user is None:
            return None
        return Principal(user.id, user.issuer, user.subject, user.display_name)

    def memberships_for(self, user_id: UUID) -> list[TenantMembership]:
        found: list[TenantMembership] = []
        for membership in self.session.scalars(
            select(Membership).where(Membership.user_id == user_id, Membership.state == "active")
        ):
            tenant = self.session.get(Tenant, membership.tenant_id)
            if tenant is None or tenant.state != "active":
                continue
            found.append(
                TenantMembership(
                    tenant_id=tenant.id,
                    slug=tenant.slug,
                    name=tenant.name,
                    role=membership.role,
                    state=membership.state,
                    authorization_version=tenant.authorization_version,
                )
            )
        return found

    def select_tenant(self, principal: Principal, tenant_id: UUID) -> AccessContext:
        tenant = self.session.get(Tenant, tenant_id)
        membership = self.session.get(Membership, (tenant_id, principal.user_id))
        if (
            tenant is None
            or tenant.state != "active"
            or membership is None
            or membership.state != "active"
        ):
            raise NotFound(HIDDEN)
        return AccessContext(
            tenant_id=tenant.id,
            actor_id=principal.user_id,
            role=membership.role,
            correlation_id=uuid4(),
            authenticated_subject=f"{principal.issuer}|{principal.subject}",
            authorization_version=tenant.authorization_version,
        )

    def _membership(self, context: AccessContext) -> Membership:
        tenant = self.session.get(Tenant, context.tenant_id)
        membership = self.session.get(Membership, (context.tenant_id, context.actor_id))
        if tenant is None or membership is None:
            raise NotFound(HIDDEN)
        if tenant.state != "active" or membership.state != "active":
            raise AccessRevoked()
        if membership.version < 0 or tenant.authorization_version < context.authorization_version:
            raise AccessRevoked()
        return membership

    def grant_for(self, context: AccessContext, repository_id: UUID) -> str | None:
        self._membership(context)
        grant = self.session.get(
            RepositoryGrant, (context.tenant_id, repository_id, context.actor_id)
        )
        return grant.permission if grant is not None else None

    def authorize(
        self,
        context: AccessContext,
        *,
        repository_id: UUID,
        action: Action,
    ) -> None:
        membership = self._membership(context)
        repository = self.session.get(Repository, (context.tenant_id, repository_id))
        if repository is None or repository.state != "active":
            raise NotFound(HIDDEN)
        if not allows(
            role=membership.role, grant=self.grant_for(context, repository_id), action=action
        ):
            if action == "read":
                raise NotFound(HIDDEN)
            raise AccessDenied(HIDDEN)

    def authorize_review(
        self,
        context: AccessContext,
        review_id: UUID,
        *,
        action: Action,
    ) -> Review:
        review = self.session.get(Review, (context.tenant_id, review_id))
        if review is None:
            raise NotFound(HIDDEN)
        self.authorize(context, repository_id=review.repository_id, action=action)
        return review

    def actor_context(self, context: AccessContext) -> ActorContext:
        return ActorContext(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            role=context.role,
            correlation_id=context.correlation_id,
            authorization_version=context.authorization_version,
        )

    def stream_open(self, context: AccessContext) -> bool:
        try:
            self._membership(context)
        except (AccessRevoked, NotFound, AccessDenied):
            return False
        return True


class Provisioner:
    def __init__(self, session: Session, *, actor_ref: str, keyring: KeyRing | None = None) -> None:
        self.session = session
        self.actor_ref = actor_ref
        self.keyring = keyring

    def _audit(
        self,
        tenant_id: UUID,
        operation: str,
        target_type: str,
        target_id: str,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.session.add(
            AdminAudit(
                tenant_id=tenant_id,
                id=uuid4(),
                actor_ref=self.actor_ref,
                operation=operation,
                target_type=target_type,
                target_id=target_id,
                redacted_detail=_redact(detail or {}),
            )
        )

    def create_tenant(self, *, slug: str, name: str) -> Tenant:
        existing = self.session.scalar(select(Tenant).where(Tenant.slug == slug))
        if existing is not None:
            raise AccessDenied("tenant slug already exists")
        tenant = Tenant(
            id=uuid4(),
            slug=slug,
            name=name,
            state="active",
            authorization_version=1,
            limits={},
        )
        self.session.add(tenant)
        self.session.flush()
        self._audit(tenant.id, "tenant.create", "tenant", str(tenant.id), {"slug": slug})
        return tenant

    def set_member(
        self,
        *,
        tenant_id: UUID,
        issuer: str,
        subject: str,
        role: str,
        display_name: str,
    ) -> Membership:
        tenant = self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFound(HIDDEN)
        user = self.session.scalar(
            select(User).where(User.issuer == issuer, User.subject == subject)
        )
        if user is None:
            same_subject = self.session.scalar(select(User).where(User.subject == subject))
            if same_subject is not None and same_subject.issuer != issuer:
                raise AccessDenied("refusing cross-issuer identity linking")
            user = User(id=uuid4(), issuer=issuer, subject=subject, display_name=display_name)
            self.session.add(user)
            self.session.flush()
        elif user.issuer != issuer:
            raise AccessDenied("refusing cross-issuer identity linking")
        membership = self.session.get(Membership, (tenant_id, user.id))
        if membership is None:
            membership = Membership(
                tenant_id=tenant_id,
                user_id=user.id,
                role=role,
                state="active",
                version=1,
            )
            self.session.add(membership)
        else:
            membership.role = role
            membership.state = "active"
            membership.version += 1
            membership.updated_at = utcnow()
        self.session.flush()
        self._audit(
            tenant_id,
            "member.set",
            "membership",
            str(user.id),
            {"issuer": issuer, "subject": subject, "role": role},
        )
        return membership

    def revoke_member(self, *, tenant_id: UUID, user_id: UUID) -> None:
        membership = self.session.get(Membership, (tenant_id, user_id))
        tenant = self.session.get(Tenant, tenant_id)
        if membership is None or tenant is None:
            raise NotFound(HIDDEN)
        membership.state = "revoked"
        membership.version += 1
        membership.updated_at = utcnow()
        tenant.authorization_version += 1
        tenant.updated_at = utcnow()
        _cancel_jobs(self.session, tenant_id, actor_id=user_id)
        self.session.flush()
        self._audit(tenant_id, "member.revoke", "membership", str(user_id), {})

    def register_repository(
        self,
        *,
        tenant_id: UUID,
        provider: str,
        host: str,
        provider_repository_id: str,
        display_name: str,
    ) -> Repository:
        existing = self.session.scalar(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.provider == provider,
                Repository.host == host,
                Repository.provider_repository_id == provider_repository_id,
            )
        )
        if existing is not None:
            return existing
        repository = Repository(
            tenant_id=tenant_id,
            id=uuid4(),
            provider=provider,
            host=host,
            provider_repository_id=provider_repository_id,
            display_name=display_name,
            state="active",
        )
        self.session.add(repository)
        self.session.flush()
        self._audit(
            tenant_id,
            "repo.register",
            "repository",
            str(repository.id),
            {"display_name": display_name},
        )
        return repository

    def set_grant(
        self,
        *,
        tenant_id: UUID,
        repository_id: UUID,
        user_id: UUID,
        permission: str,
    ) -> RepositoryGrant:
        if self.session.get(Repository, (tenant_id, repository_id)) is None:
            raise NotFound(HIDDEN)
        if self.session.get(Membership, (tenant_id, user_id)) is None:
            raise NotFound(HIDDEN)
        grant = self.session.get(RepositoryGrant, (tenant_id, repository_id, user_id))
        if grant is None:
            grant = RepositoryGrant(
                tenant_id=tenant_id,
                repository_id=repository_id,
                user_id=user_id,
                permission=permission,
                version=1,
            )
            self.session.add(grant)
        else:
            grant.permission = permission
            grant.version += 1
        self.session.flush()
        self._audit(
            tenant_id,
            "grant.set",
            "grant",
            f"{repository_id}:{user_id}",
            {"permission": permission},
        )
        return grant

    def revoke_grant(self, *, tenant_id: UUID, repository_id: UUID, user_id: UUID) -> None:
        grant = self.session.get(RepositoryGrant, (tenant_id, repository_id, user_id))
        if grant is None:
            raise NotFound(HIDDEN)
        self.session.delete(grant)
        _cancel_jobs(self.session, tenant_id, actor_id=user_id)
        self.session.flush()
        self._audit(tenant_id, "grant.revoke", "grant", f"{repository_id}:{user_id}", {})

    def set_credential(
        self,
        *,
        tenant_id: UUID,
        kind: str,
        secret: str,
        owner_user_id: UUID | None,
        provider_host: str,
        verified_login: str | None = None,
    ) -> Credential:
        if self.keyring is None:
            raise AccessDenied("key ring required")
        if kind == "github" and owner_user_id is None:
            raise AccessDenied("github credential requires a user")
        current = _active_credential(self.session, tenant_id, kind, owner_user_id, provider_host)
        credential_id = uuid4()
        version = current.version + 1 if current is not None else 1
        aad = associated_data(
            tenant_id=tenant_id,
            credential_id=credential_id,
            owner_user_id=owner_user_id,
            kind=kind,
            version=version,
        )
        ciphertext, nonce, key_id = encrypt_secret(self.keyring, secret.encode(), aad)
        if current is not None:
            current.state = "revoked"
            current.updated_at = utcnow()
        credential = Credential(
            tenant_id=tenant_id,
            id=credential_id,
            kind=kind,
            owner_user_id=owner_user_id,
            provider_host=provider_host,
            ciphertext=ciphertext,
            nonce=nonce,
            key_id=key_id,
            version=version,
            state="active",
            verified_login=verified_login,
        )
        self.session.add(credential)
        self.session.flush()
        self._audit(
            tenant_id,
            "credential.set",
            "credential",
            str(credential.id),
            {"kind": kind, "key_id": key_id, "version": version, "login": verified_login},
        )
        return credential

    def revoke_credential(self, *, tenant_id: UUID, credential_id: UUID) -> None:
        credential = self.session.get(Credential, (tenant_id, credential_id))
        if credential is None:
            raise NotFound(HIDDEN)
        credential.state = "revoked"
        credential.updated_at = utcnow()
        kinds = (
            frozenset({"acquire", "refresh"})
            if credential.kind == "github"
            else frozenset({"analyze"})
        )
        _cancel_jobs(self.session, tenant_id, actor_id=credential.owner_user_id, kinds=kinds)
        self.session.flush()
        self._audit(
            tenant_id,
            "credential.revoke",
            "credential",
            str(credential_id),
            {"kind": credential.kind, "version": credential.version},
        )

    def reveal_credential(self, *, tenant_id: UUID, credential_id: UUID) -> bytes:
        if self.keyring is None:
            raise AccessDenied("key ring required")
        credential = self.session.get(Credential, (tenant_id, credential_id))
        if credential is None or credential.state != "active":
            raise NotFound(HIDDEN)
        aad = associated_data(
            tenant_id=tenant_id,
            credential_id=credential.id,
            owner_user_id=credential.owner_user_id,
            kind=credential.kind,
            version=credential.version,
        )
        return decrypt_secret(
            self.keyring,
            ciphertext=credential.ciphertext,
            nonce=credential.nonce,
            key_id=credential.key_id,
            aad=aad,
        )


def workspace_for(session: Session, context: AccessContext) -> TenantWorkspace:
    return TenantWorkspace(
        session,
        ActorContext(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            role=context.role,
            correlation_id=context.correlation_id,
            authorization_version=context.authorization_version,
        ),
    )


def _active_credential(
    session: Session,
    tenant_id: UUID,
    kind: str,
    owner_user_id: UUID | None,
    provider_host: str,
) -> Credential | None:
    query = select(Credential).where(
        Credential.tenant_id == tenant_id,
        Credential.kind == kind,
        Credential.provider_host == provider_host,
        Credential.state == "active",
    )
    if kind == "github":
        query = query.where(Credential.owner_user_id == owner_user_id)
    return session.scalar(query)


def _cancel_jobs(
    session: Session,
    tenant_id: UUID,
    *,
    actor_id: UUID | None = None,
    kinds: frozenset[str] | None = None,
) -> None:
    rows = list(
        session.scalars(
            select(Job).where(Job.tenant_id == tenant_id, Job.status.in_(("queued", "running")))
        )
    )
    now = utcnow()
    for job in rows:
        if actor_id is not None and job.actor_id != actor_id:
            continue
        if kinds is not None and job.kind not in kinds:
            continue
        job.status = "cancelled"
        job.cancel_requested_at = now
        job.updated_at = now


def _redact(detail: dict[str, object]) -> dict[str, object]:
    blocked = {"secret", "token", "ciphertext", "authorization", "password", "nonce"}
    redacted: dict[str, object] = {}
    for key, value in detail.items():
        if key.lower() in blocked or any(word in key.lower() for word in blocked):
            redacted[key] = "[redacted]"
        elif isinstance(value, str) and len(value) > 24 and value.startswith(("ghp_", "gho_")):
            redacted[key] = "[redacted]"
        else:
            redacted[key] = value
    return redacted
