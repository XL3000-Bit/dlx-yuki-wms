"""company profile singleton

Revision ID: 20260901_0021
Revises: 20260830_0020
"""
from alembic import op
import sqlalchemy as sa

revision = "20260901_0021"
down_revision = "20260830_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_name", sa.String(200), nullable=False, server_default="DLX"),
        sa.Column("brand_name", sa.String(200), nullable=False, server_default="Yuki WMS"),
        sa.Column("legal_name", sa.String(200), nullable=False, server_default="DLX"),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("city", sa.String(100), nullable=False, server_default=""),
        sa.Column("state", sa.String(50), nullable=False, server_default="CA"),
        sa.Column("zip_code", sa.String(20), nullable=False, server_default=""),
        sa.Column("country", sa.String(2), nullable=False, server_default="US"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Los_Angeles"),
        sa.Column("default_warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        """
        INSERT INTO company_profiles (
            company_name, brand_name, legal_name, email, phone, address, city, state, zip_code, country, timezone
        )
        SELECT 'DLX', 'Yuki WMS', 'DLX', '', '', '', '', 'CA', '', 'US', 'America/Los_Angeles'
        WHERE NOT EXISTS (SELECT 1 FROM company_profiles)
        """
    )


def downgrade() -> None:
    op.drop_table("company_profiles")
