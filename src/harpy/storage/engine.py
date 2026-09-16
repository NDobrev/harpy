"""SQLAlchemy engine helpers for local SQLite and hosted PostgreSQL."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from harpy.storage.schema import install_schema

_SQLITE_BUSY_MS = 5000


class SqliteUnavailableError(RuntimeError):
    pass


def sqlite_module() -> ModuleType:
    try:
        import sqlite3

        sqlite3.connect(":memory:").close()
        return sqlite3
    except Exception:
        pass
    try:
        import pysqlite3 as sqlite3_fallback  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SqliteUnavailableError(
            f"{sys.executable} has no SQLite support. Install a Python with "
            "_sqlite3 or the web extra (pysqlite3-binary), then rebuild the environment."
        ) from exc
    return sqlite3_fallback  # type: ignore[no-any-return]


def sqlite_url(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{path}"


def create_sqlite_engine(path: Path) -> Engine:
    engine = create_engine(
        sqlite_url(path),
        future=True,
        module=sqlite_module(),
        connect_args={"timeout": _SQLITE_BUSY_MS / 1000, "check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_MS}")
        cursor.close()

    return engine


def create_postgres_engine(url: str) -> Engine:
    return create_engine(url, future=True, pool_pre_ping=True)


def initialize_engine(engine: Engine) -> None:
    with engine.begin() as connection:
        install_schema(connection)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_tenant_guc(session: Session, tenant_id: object | None) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    value = "" if tenant_id is None else str(tenant_id)
    session.execute(
        text("SELECT set_config('harpy.tenant_id', :tenant_id, true)"), {"tenant_id": value}
    )
