"""Apply forward-only schema migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from harpy.storage.schema import install_schema

PACKAGE_ROOT = Path(__file__).resolve().parent


def alembic_config(url: str) -> Config:
    config = Config(str(PACKAGE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PACKAGE_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade_head(url: str) -> None:
    if url.startswith("sqlite"):
        from harpy.storage.engine import create_sqlite_engine, initialize_engine

        path = Path(url.split("///", 1)[1])
        engine = create_sqlite_engine(path)
        initialize_engine(engine)
        engine.dispose()
        return
    command.upgrade(alembic_config(url), "head")


def install_engine_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        install_schema(connection)
