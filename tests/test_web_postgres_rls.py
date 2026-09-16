from __future__ import annotations

import os
import socket
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from harpy.proc import run, which
from harpy.storage.engine import set_tenant_guc
from harpy.storage.schema import install_schema
from harpy.storage.workspace import TenantWorkspace, create_local_graph

POSTGRES_HINT = (
    "PostgreSQL 16+ is required for AT-032. Install server binaries "
    "(initdb and pg_ctl) and rerun make setup. Hosted Harpy uses PostgreSQL 18."
)


def _postgres_bin() -> Path:
    initdb = which("initdb")
    if initdb is not None:
        return initdb.parent
    for candidate in Path("/usr/lib/postgresql").glob("*/bin/initdb"):
        return candidate.parent
    pytest.fail(POSTGRES_HINT)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_postgres(tmp_path: Path) -> tuple[Path, str]:
    bindir = _postgres_bin()
    data = tmp_path / "pgdata"
    port = _free_port()
    env = {"PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}", "TZ": "UTC"}
    initialized = run(
        [
            str(bindir / "initdb"),
            "-D",
            str(data),
            "--auth-local=trust",
            "--auth-host=trust",
            "-U",
            "postgres",
        ],
        timeout=30,
        env=env,
        inherit_env=True,
    )
    if not initialized.ok:
        pytest.fail(f"{POSTGRES_HINT} initdb failed: {initialized.stderr}")
    socket_dir = tmp_path / "pgsocket"
    socket_dir.mkdir()
    log_file = tmp_path / "postgres.log"
    started = run(
        [
            str(bindir / "pg_ctl"),
            "-D",
            str(data),
            "-l",
            str(log_file),
            "-o",
            (f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories={socket_dir}"),
            "-w",
            "start",
        ],
        timeout=30,
        env=env,
        inherit_env=True,
    )
    if not started.ok:
        log_text = log_file.read_text(encoding="utf-8") if log_file.is_file() else ""
        pytest.fail(f"{POSTGRES_HINT} pg_ctl start failed: {started.stderr}\n{log_text}")
    return data, f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres"


def _stop_postgres(bindir: Path, data: Path) -> None:
    run(
        [str(bindir / "pg_ctl"), "-D", str(data), "-m", "fast", "stop"],
        timeout=15,
        inherit_env=True,
        check=False,
    )


def test_at_032_postgres_rls_denies_missing_and_foreign_tenant(tmp_path: Path) -> None:
    bindir = _postgres_bin()
    data, admin_url = _start_postgres(tmp_path)
    try:
        admin = create_engine(admin_url, future=True)
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(
                text("CREATE ROLE harpy_app LOGIN PASSWORD 'app' NOSUPERUSER NOBYPASSRLS")
            )
        owner = create_engine(admin_url, future=True)
        with owner.begin() as connection:
            install_schema(connection)
            connection.execute(text("GRANT USAGE ON SCHEMA public TO harpy_app"))
            connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO harpy_app"
                )
            )
        owner_session = sessionmaker(bind=owner, future=True, expire_on_commit=False)()
        context, _review_id, report_id, change_id = create_local_graph(owner_session, slug="rls")
        workspace = TenantWorkspace(owner_session, context)
        workspace.set_decision(
            report_id=report_id,
            change_id=change_id,
            status="reviewed",
            expected_version=0,
            idempotency_key=uuid4(),
        )
        owner_session.commit()
        owner_session.close()

        app = create_engine(admin_url.replace("postgres@", "harpy_app:app@"), future=True)
        app_session = sessionmaker(bind=app, future=True, expire_on_commit=False)()
        set_tenant_guc(app_session, None)
        assert app_session.execute(text("SELECT count(*) FROM reports")).scalar_one() == 0
        set_tenant_guc(app_session, uuid4())
        assert app_session.execute(text("SELECT count(*) FROM reports")).scalar_one() == 0
        set_tenant_guc(app_session, context.tenant_id)
        assert app_session.execute(text("SELECT count(*) FROM reports")).scalar_one() == 1
        with pytest.raises(DBAPIError):
            app_session.execute(
                text(
                    "INSERT INTO reports (tenant_id, id, review_id, snapshot_id, kind, "
                    "schema_version, content_digest, config_digest, scope_summary, provenance, created_at) "
                    "VALUES (:tenant, :id, :review, :snapshot, 'static', 2, :digest, :digest, '{}', '{}', now())"
                ),
                {
                    "tenant": str(uuid4()),
                    "id": str(uuid4()),
                    "review": str(uuid4()),
                    "snapshot": str(uuid4()),
                    "digest": "a" * 64,
                },
            )
            app_session.commit()
        app_session.rollback()
        app_session.close()
        owner.dispose()
        app.dispose()
        admin.dispose()
    finally:
        _stop_postgres(bindir, data)
