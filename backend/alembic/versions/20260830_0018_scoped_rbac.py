"""scoped RBAC foundation

Revision ID: 20260830_0018
Revises: 20260830_0017
"""
from alembic import op
import sqlalchemy as sa

revision = "20260830_0018"; down_revision = "20260830_0017"; branch_labels = None; depends_on = None


def upgrade():
    scope_mode = sa.Enum("ALL", "SELECTED", name="scope_mode")
    scope_mode.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("warehouse_scope_mode", scope_mode, nullable=False, server_default="ALL"))
    op.add_column("users", sa.Column("customer_scope_mode", scope_mode, nullable=False, server_default="ALL"))
    op.create_table("user_warehouse_scopes",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("user_customer_scopes",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True))


def downgrade():
    op.drop_table("user_customer_scopes")
    op.drop_table("user_warehouse_scopes")
    op.drop_column("users", "customer_scope_mode")
    op.drop_column("users", "warehouse_scope_mode")
    sa.Enum(name="scope_mode").drop(op.get_bind(), checkfirst=True)
