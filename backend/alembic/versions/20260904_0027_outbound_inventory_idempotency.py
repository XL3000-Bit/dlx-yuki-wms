"""add outbound inventory idempotency receipts

Revision ID: 20260904_0027
Revises: 20260904_0026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260904_0027"
down_revision = "20260904_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbound_inventory_idempotency",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "action", "idempotency_key", name="uq_outbound_inventory_idempotency_command"),
    )


def downgrade() -> None:
    op.drop_table("outbound_inventory_idempotency")
