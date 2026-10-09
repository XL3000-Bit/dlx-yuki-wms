"""Persistent cargo BOL identities and document snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0031"
down_revision = "20260909_0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cargo_bols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inbound_id", sa.Integer(), sa.ForeignKey("inbound_records.id", ondelete="CASCADE"), unique=True),
        sa.Column("fba_shipment_id", sa.Integer(), sa.ForeignKey("fba_shipments.id", ondelete="CASCADE"), unique=True),
        sa.Column("history_outbound_id", sa.Integer(), sa.ForeignKey("outbound_orders.id", ondelete="CASCADE"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("(CASE WHEN inbound_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN fba_shipment_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN history_outbound_id IS NOT NULL THEN 1 ELSE 0 END) = 1", name="exactly_one_source"),
    )
    op.add_column("outbound_inventory_allocations", sa.Column("cargo_bol_id", sa.Integer(), sa.ForeignKey("cargo_bols.id", ondelete="RESTRICT")))
    op.create_index("ix_outbound_inventory_allocations_cargo_bol_id", "outbound_inventory_allocations", ["cargo_bol_id"])
    for table in ("bol_items", "picking_list_items"):
        op.add_column(table, sa.Column("cargo_bol_no", sa.String(24)))
        op.add_column(table, sa.Column("po_number", sa.Text()))


def downgrade():
    for table in ("bol_items", "picking_list_items"):
        op.drop_column(table, "po_number")
        op.drop_column(table, "cargo_bol_no")
    op.drop_index("ix_outbound_inventory_allocations_cargo_bol_id", table_name="outbound_inventory_allocations")
    op.drop_column("outbound_inventory_allocations", "cargo_bol_id")
    op.drop_table("cargo_bols")
