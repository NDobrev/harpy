"""Install the tenant-aware review schema.

Revision ID: 0001
Revises:
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from harpy.storage.schema import install_schema

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    install_schema(op.get_bind())


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
