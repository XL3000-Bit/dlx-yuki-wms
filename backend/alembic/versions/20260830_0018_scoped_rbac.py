"""scoped rbac warehouse and customer visibility foundation

Revision ID: 20260830_0018
Revises: 20260830_0017
"""
from alembic import op
import sqlalchemy as sa

revision = "20260830_0018"
down_revision = "20260830_0017"
branch_labels = None
depends_on = None


def upgrade():
    warehouse_mode = sa.Enum("ALL", "SELECTED", name="user_warehouse_scope_mode")
    customer_mode = sa.Enum("ALL", "SELECTED", name="user_customer_scope_mode")
    warehouse_mode.create(op.get_bind(), checkfirst=True)
    customer_mode.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("warehouse_scope_mode", warehouse_mode, nullable=False, server_default="ALL"))
    op.add_column("users", sa.Column("customer_scope_mode", customer_mode, nullable=False, server_default="ALL"))
    op.create_table(
        "user_warehouse_scopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "warehouse_id", name="uq_user_warehouse_scope"),
    )
    op.create_index("ix_user_warehouse_scopes_user_id", "user_warehouse_scopes", ["user_id"])
    op.create_index("ix_user_warehouse_scopes_warehouse_id", "user_warehouse_scopes", ["warehouse_id"])
    op.create_table(
        "user_customer_scopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "customer_id", name="uq_user_customer_scope"),
    )
    op.create_index("ix_user_customer_scopes_user_id", "user_customer_scopes", ["user_id"])
    op.create_index("ix_user_customer_scopes_customer_id", "user_customer_scopes", ["customer_id"])
    op.execute("UPDATE users SET warehouse_scope_mode = 'ALL', customer_scope_mode = 'ALL'")


def downgrade():
    op.drop_table("user_customer_scopes")
    op.drop_table("user_warehouse_scopes")
    op.drop_column("users", "customer_scope_mode")
    op.drop_column("users", "warehouse_scope_mode")
    sa.Enum(name="user_customer_scope_mode").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_warehouse_scope_mode").drop(op.get_bind(), checkfirst=True)
