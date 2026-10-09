"""Phase 10.9 RC schema alignment.

Revision ID: 20260830_0021
Revises: 20260830_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260830_0021"
down_revision: str | None = "20260830_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "operational_exceptions",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.func.now(),
    )
    op.alter_column(
        "operational_exceptions",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.func.now(),
    )


def downgrade() -> None:
    op.alter_column(
        "operational_exceptions",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "operational_exceptions",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=None,
    )
