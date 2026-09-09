"""add multi-line inbound receiving

Revision ID: 20260908_0029
Revises: 20260904_0028
"""
from alembic import op
import sqlalchemy as sa


revision = "20260908_0029"
down_revision = "20260904_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inbound_id", sa.Integer(), sa.ForeignKey("inbound_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("fc_code", sa.String(20)),
        sa.Column("pallet_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("carton_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("weight_lbs", sa.Numeric(14, 2)),
        sa.Column("cbm", sa.Numeric(14, 4)),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("warehouse_locations.id", ondelete="RESTRICT")),
        sa.Column("remark", sa.Text()),
        sa.UniqueConstraint("inbound_id", "line_no", name="uq_inbound_lines_inbound_line_no"),
        sa.CheckConstraint("pallet_qty >= 0", name="ck_inbound_lines_pallet_non_negative"),
        sa.CheckConstraint("carton_qty >= 0", name="ck_inbound_lines_carton_non_negative"),
        sa.CheckConstraint("weight_lbs IS NULL OR weight_lbs >= 0", name="ck_inbound_lines_weight_non_negative"),
        sa.CheckConstraint("cbm IS NULL OR cbm >= 0", name="ck_inbound_lines_cbm_non_negative"),
    )
    for column in ("inbound_id", "fc_code", "location_id"):
        op.create_index(f"ix_inbound_lines_{column}", "inbound_lines", [column])

    connection = op.get_bind()
    connection.execute(sa.text(
        "INSERT INTO inbound_lines "
        "(inbound_id, line_no, fc_code, pallet_qty, carton_qty, weight_lbs, cbm, location_id, remark) "
        "SELECT id, 1, fc_code, pallet_qty, carton_qty, weight_lbs, cbm, location_id, remark "
        "FROM inbound_records"
    ))

    op.add_column("inventory_lots", sa.Column("inbound_line_id", sa.Integer()))
    op.create_foreign_key(
        "fk_inventory_lots_inbound_line_id_inbound_lines",
        "inventory_lots", "inbound_lines", ["inbound_line_id"], ["id"], ondelete="RESTRICT",
    )
    connection.execute(sa.text(
        "UPDATE inventory_lots AS lot SET inbound_line_id = line.id "
        "FROM inbound_lines AS line "
        "WHERE line.inbound_id = lot.source_inbound_id AND line.line_no = 1"
    ))
    op.create_index("ix_inventory_lots_inbound_line_id", "inventory_lots", ["inbound_line_id"], unique=True)

    op.drop_index("ix_inventory_lots_source_inbound_id", table_name="inventory_lots")
    op.drop_constraint("uq_inventory_lots_source_inbound_id", "inventory_lots", type_="unique")
    op.create_index("ix_inventory_lots_source_inbound_id", "inventory_lots", ["source_inbound_id"])

    op.drop_constraint("ck_inbound_records_status_range", "inbound_records", type_="check")
    op.create_check_constraint("ck_inbound_records_status_range", "inbound_records", "status BETWEEN 0 AND 6")


def downgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(sa.text(
        "SELECT source_inbound_id FROM inventory_lots GROUP BY source_inbound_id HAVING count(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(f"Cannot downgrade: inbound {duplicate[0]} has multiple inventory lots")

    op.drop_constraint("ck_inbound_records_status_range", "inbound_records", type_="check")
    op.create_check_constraint("ck_inbound_records_status_range", "inbound_records", "status BETWEEN 0 AND 5")
    op.drop_index("ix_inventory_lots_source_inbound_id", table_name="inventory_lots")
    op.create_unique_constraint("uq_inventory_lots_source_inbound_id", "inventory_lots", ["source_inbound_id"])
    op.create_index("ix_inventory_lots_source_inbound_id", "inventory_lots", ["source_inbound_id"], unique=True)
    op.drop_index("ix_inventory_lots_inbound_line_id", table_name="inventory_lots")
    op.drop_constraint("fk_inventory_lots_inbound_line_id_inbound_lines", "inventory_lots", type_="foreignkey")
    op.drop_column("inventory_lots", "inbound_line_id")
    op.drop_table("inbound_lines")
