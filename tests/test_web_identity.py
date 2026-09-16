from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from harpy.identity.access import allows
from harpy.identity.local import LocalAuthenticator, implicit_principal
from harpy.identity.oidc import OidcAuthenticator, OidcConfig, rsa_jwks, sign_rs256
from harpy.identity.types import (
    AccessContext,
    AccessDenied,
    AccessRevoked,
    AuthenticationError,
    NotFound,
)
from harpy.storage.access import AccessDirectory, Provisioner, workspace_for
from harpy.storage.engine import create_sqlite_engine, initialize_engine
from harpy.storage.schema import AdminAudit, Review
from harpy.storage.secrets import (
    SecretError,
    generate_keyring,
    hosted_github_environ,
    refuse_ambient_github,
)
from harpy.storage.workspace import create_local_graph


def _now() -> datetime:
    return datetime(2026, 9, 16, 12, tzinfo=UTC)


def _engine(tmp_path: Path) -> Engine:
    engine = create_sqlite_engine(tmp_path / "harpy.sqlite3")
    initialize_engine(engine)
    return engine


def test_at_028_local_bootstrap_is_one_time_and_origin_bound() -> None:
    clock = {"now": _now()}
    auth = LocalAuthenticator(
        public_origin="http://127.0.0.1:8765",
        port=8765,
        principal=implicit_principal(),
        clock=lambda: clock["now"],
    )
    url = auth.issue_bootstrap()
    assert url.startswith("http://127.0.0.1:8765/#bootstrap=")
    assert "?" not in url
    token = url.rsplit("=", 1)[1]
    with pytest.raises(AuthenticationError, match="query"):
        auth.exchange(
            token, host="127.0.0.1:8765", origin="http://127.0.0.1:8765", query={"token": token}
        )
    with pytest.raises(AuthenticationError, match="host"):
        auth.exchange(token, host="evil.example:8765", origin="http://127.0.0.1:8765")
    with pytest.raises(AuthenticationError, match="origin"):
        auth.exchange(token, host="127.0.0.1:8765", origin="https://evil.example")
    session = auth.exchange(token, host="127.0.0.1:8765", origin="http://127.0.0.1:8765")
    with pytest.raises(AuthenticationError, match="invalid"):
        auth.exchange(token, host="127.0.0.1:8765", origin="http://127.0.0.1:8765")
    with pytest.raises(AuthenticationError, match="csrf"):
        auth.authorize_unsafe(
            session.session_id,
            method="POST",
            host="127.0.0.1:8765",
            origin="http://127.0.0.1:8765",
            headers={},
        )
    auth.authorize_unsafe(
        session.session_id,
        method="POST",
        host="127.0.0.1:8765",
        origin="http://127.0.0.1:8765",
        headers={"X-CSRF-Token": session.csrf_token},
    )
    late = auth.issue_bootstrap()
    clock["now"] = _now() + timedelta(minutes=6)
    with pytest.raises(AuthenticationError, match="invalid"):
        auth.exchange(late.rsplit("=", 1)[1], host="127.0.0.1:8765", origin="http://127.0.0.1:8765")


def test_at_027_oidc_membership_and_spoofed_headers() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks = rsa_jwks(key, kid="k1")
    config = OidcConfig(issuer="https://issuer.example", audience="harpy")
    auth = OidcAuthenticator(config, jwks=jwks, clock=_now)
    exp = int((_now() + timedelta(hours=1)).timestamp())
    good = sign_rs256(
        {"iss": config.issuer, "aud": config.audience, "sub": "user-1", "exp": exp},
        private_key=key,
        kid="k1",
    )
    claims = auth.authenticate({"Authorization": f"Bearer {good}", "X-Forwarded-User": "attacker"})
    assert claims.subject == "user-1"
    with pytest.raises(AuthenticationError, match="missing bearer"):
        auth.authenticate({"X-Forwarded-User": "user-1", "X-Tenant-ID": str(uuid4())})
    wrong_iss = sign_rs256(
        {"iss": "https://other.example", "aud": config.audience, "sub": "user-1", "exp": exp},
        private_key=key,
        kid="k1",
    )
    with pytest.raises(AuthenticationError, match="issuer"):
        auth.verify(wrong_iss)
    wrong_aud = sign_rs256(
        {"iss": config.issuer, "aud": "other", "sub": "user-1", "exp": exp},
        private_key=key,
        kid="k1",
    )
    with pytest.raises(AuthenticationError, match="audience"):
        auth.verify(wrong_aud)
    expired = sign_rs256(
        {
            "iss": config.issuer,
            "aud": config.audience,
            "sub": "user-1",
            "exp": int((_now() - timedelta(hours=2)).timestamp()),
        },
        private_key=key,
        kid="k1",
    )
    with pytest.raises(AuthenticationError, match="expired"):
        auth.verify(expired)
    none_header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIiwia2lkIjoiazEifQ." + good.split(".", 1)[1]
    with pytest.raises(AuthenticationError, match="algorithm"):
        auth.verify(none_header)


def test_at_027_logout_and_unknown_user(tmp_path: Path) -> None:
    auth = LocalAuthenticator(
        public_origin="http://127.0.0.1:8765",
        port=8765,
        principal=implicit_principal(),
    )
    token = auth.issue_bootstrap().rsplit("=", 1)[1]
    session = auth.exchange(token, host="127.0.0.1:8765", origin="http://127.0.0.1:8765")
    auth.logout(session.session_id)
    with pytest.raises(AuthenticationError, match="expired"):
        auth.resolve(session.session_id)
    engine = _engine(tmp_path)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    try:
        create_local_graph(db, slug="acme")
        db.commit()
        directory = AccessDirectory(db)
        assert directory.principal_for("https://issuer.example", "nobody") is None
    finally:
        db.close()
        engine.dispose()


def test_at_029_role_and_grant_matrix(tmp_path: Path) -> None:
    assert allows(role="viewer", grant="review", action="mutate") is False
    assert allows(role="reviewer", grant="read", action="mutate") is False
    assert allows(role="reviewer", grant="review", action="mutate") is True
    assert allows(role="administrator", grant=None, action="read") is False
    engine = _engine(tmp_path)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    try:
        context, review_id, _report_id, _change_id = create_local_graph(db, slug="acme")
        provisioner = Provisioner(db, actor_ref="operator")
        viewer = provisioner.set_member(
            tenant_id=context.tenant_id,
            issuer="https://issuer.example",
            subject="viewer",
            role="viewer",
            display_name="Viewer",
        )
        other = provisioner.create_tenant(slug="other", name="Other")
        directory = AccessDirectory(db)
        principal = directory.principal_for("https://issuer.example", "viewer")
        assert principal is not None
        access = directory.select_tenant(principal, context.tenant_id)
        review = db.get(Review, (context.tenant_id, review_id))
        assert review is not None
        provisioner.set_grant(
            tenant_id=context.tenant_id,
            repository_id=review.repository_id,
            user_id=viewer.user_id,
            permission="review",
        )
        with pytest.raises(AccessDenied):
            directory.authorize(access, repository_id=review.repository_id, action="mutate")
        directory.authorize(access, repository_id=review.repository_id, action="read")
        with pytest.raises(NotFound) as missing:
            directory.authorize_review(access, uuid4(), action="read")
        with pytest.raises(NotFound) as foreign:
            directory.select_tenant(principal, other.id)
        assert str(missing.value) == str(foreign.value) == "not found"
        db.commit()
    finally:
        db.close()
        engine.dispose()


def test_at_030_revocation_closes_stream_and_cancels_jobs(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    try:
        context, review_id, _report_id, _change_id = create_local_graph(db, slug="acme")
        access = AccessContext(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            role=context.role,
            correlation_id=context.correlation_id,
            authenticated_subject="local|implicit",
            authorization_version=context.authorization_version,
        )
        workspace = workspace_for(db, access)
        queued = workspace.put_job(
            kind="analyze",
            status="queued",
            phase="waiting",
            dedupe_key="q1",
            review_id=review_id,
        )
        running = workspace.put_job(
            kind="analyze",
            status="running",
            phase="analyzing",
            dedupe_key="r1",
            review_id=review_id,
        )
        directory = AccessDirectory(db)
        assert directory.stream_open(access) is True
        Provisioner(db, actor_ref="operator").revoke_member(
            tenant_id=context.tenant_id, user_id=context.actor_id
        )
        assert directory.stream_open(access) is False
        with pytest.raises(AccessRevoked):
            directory.authorize_review(access, review_id, action="read")
        db.refresh(queued)
        db.refresh(running)
        assert queued.status == "cancelled"
        assert running.status == "cancelled"
        assert running.cancel_requested_at is not None
        db.commit()
    finally:
        db.close()
        engine.dispose()


def test_at_033_credentials_are_encrypted_and_not_ambient(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    ring = generate_keyring()
    try:
        context, _review_id, _report_id, _change_id = create_local_graph(db, slug="acme")
        provisioner = Provisioner(db, actor_ref="operator", keyring=ring)
        first = provisioner.set_credential(
            tenant_id=context.tenant_id,
            kind="github",
            secret="ghp_supersecret_value_one",
            owner_user_id=context.actor_id,
            provider_host="github.com",
            verified_login="ada",
        )
        assert first.ciphertext != "ghp_supersecret_value_one"
        assert "ghp_" not in first.ciphertext
        rotated = provisioner.set_credential(
            tenant_id=context.tenant_id,
            kind="github",
            secret="ghp_supersecret_value_two",
            owner_user_id=context.actor_id,
            provider_host="github.com",
            verified_login="ada",
        )
        assert rotated.version == 2
        assert provisioner.reveal_credential(
            tenant_id=context.tenant_id, credential_id=rotated.id
        ) == (b"ghp_supersecret_value_two")
        access = AccessContext(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            role=context.role,
            correlation_id=context.correlation_id,
            authenticated_subject="local|implicit",
            authorization_version=1,
        )
        workspace = workspace_for(db, access)
        job = workspace.put_job(kind="acquire", status="queued", phase="waiting", dedupe_key="a1")
        provisioner.revoke_credential(tenant_id=context.tenant_id, credential_id=rotated.id)
        db.refresh(job)
        assert job.status == "cancelled"
        audits = list(db.scalars(select(AdminAudit)))
        blob = str([item.redacted_detail for item in audits])
        assert "ghp_supersecret" not in blob
        assert "[redacted]" in blob or "github" in blob
        refuse_ambient_github({})
        with pytest.raises(SecretError, match="ambient"):
            refuse_ambient_github({"GH_TOKEN": "ghp_home"})
        env = hosted_github_environ("ghp_job")
        assert env["GH_TOKEN"] == "ghp_job"
        assert env["GH_CONFIG_DIR"] == "/var/empty/harpy-gh"
        db.commit()
    finally:
        db.close()
        engine.dispose()


def test_provisioner_refuses_cross_issuer_link(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    try:
        context, _review_id, _report_id, _change_id = create_local_graph(db, slug="acme")
        provisioner = Provisioner(db, actor_ref="operator")
        provisioner.set_member(
            tenant_id=context.tenant_id,
            issuer="https://issuer-a.example",
            subject="same-sub",
            role="reviewer",
            display_name="Ada",
        )
        with pytest.raises(AccessDenied, match="cross-issuer"):
            provisioner.set_member(
                tenant_id=context.tenant_id,
                issuer="https://issuer-b.example",
                subject="same-sub",
                role="reviewer",
                display_name="Ada",
            )
        db.commit()
    finally:
        db.close()
        engine.dispose()
