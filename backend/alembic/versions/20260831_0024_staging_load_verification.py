"""staging load verification

Revision ID: 20260831_0024
Revises: 20260830_0023
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0024"
down_revision: str | None = "20260830_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("stage_transactions",
        sa.Column("id",sa.Integer(),nullable=False),sa.Column("load_id",sa.Integer(),nullable=False),
        sa.Column("outbound_id",sa.Integer(),nullable=False),sa.Column("picking_item_id",sa.Integer(),nullable=False),
        sa.Column("staging_location_id",sa.Integer(),nullable=False),sa.Column("action",sa.String(10),nullable=False),
        sa.Column("quantity",sa.Numeric(12,2),nullable=False),sa.Column("quantity_unit",sa.String(20),nullable=False),
        sa.Column("client_operation_id",sa.String(64),nullable=True),sa.Column("performed_by",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint("action IN ('STAGE','UNSTAGE')",name="action_values"),
        sa.CheckConstraint("quantity > 0",name="quantity_positive"),
        sa.CheckConstraint("quantity_unit IN ('PALLET','CARTON')",name="quantity_unit_values"),
        sa.ForeignKeyConstraint(["load_id"],["loads.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["outbound_id"],["outbound_orders.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["picking_item_id"],["picking_list_items.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["staging_location_id"],["warehouse_locations.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["performed_by"],["users.id"],ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("client_operation_id"))
    for col in ("load_id","outbound_id","picking_item_id","staging_location_id","performed_by"):
        op.create_index(f"ix_stage_transactions_{col}","stage_transactions",[col])
    op.create_table("load_verification_transactions",
        sa.Column("id",sa.Integer(),nullable=False),sa.Column("verification_run_id",sa.String(36),nullable=False),
        sa.Column("load_id",sa.Integer(),nullable=False),sa.Column("transaction_type",sa.String(12),nullable=False),
        sa.Column("outbound_id",sa.Integer(),nullable=True),sa.Column("picking_item_id",sa.Integer(),nullable=True),
        sa.Column("quantity",sa.Numeric(12,2),nullable=True),sa.Column("quantity_unit",sa.String(20),nullable=True),
        sa.Column("result",sa.String(20),nullable=False),sa.Column("client_operation_id",sa.String(64),nullable=True),
        sa.Column("manifest_fingerprint",sa.String(64),nullable=True),sa.Column("performed_by",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint("transaction_type IN ('START','SCAN','COMPLETE')",name="transaction_type_values"),
        sa.ForeignKeyConstraint(["load_id"],["loads.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["outbound_id"],["outbound_orders.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["picking_item_id"],["picking_list_items.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["performed_by"],["users.id"],ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("client_operation_id"))
    for col in ("verification_run_id","load_id","outbound_id","picking_item_id","manifest_fingerprint","performed_by"):
        op.create_index(f"ix_load_verification_transactions_{col}","load_verification_transactions",[col])


def downgrade() -> None:
    op.drop_table("load_verification_transactions")
    op.drop_table("stage_transactions")
