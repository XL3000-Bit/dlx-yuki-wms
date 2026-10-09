"""phase 10.1 load management foundation"""
from alembic import op
import sqlalchemy as sa

revision = "20260829_0013"
down_revision = "20260828_0012"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "loads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("load_no", sa.String(32), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("carrier_id", sa.Integer(), sa.ForeignKey("carriers.id", ondelete="RESTRICT")),
        sa.Column("status", sa.Enum("PLANNED", "READY", "DISPATCHED", "COMPLETED", "CANCELED", name="load_status"), nullable=False),
        sa.Column("appointment_reference", sa.String(100)), sa.Column("appointment_time", sa.DateTime(timezone=True)),
        sa.Column("destination_name", sa.String(200)), sa.Column("destination_address", sa.Text()),
        sa.Column("driver_name", sa.String(100)), sa.Column("driver_phone", sa.String(50)), sa.Column("tractor_no", sa.String(50)), sa.Column("trailer_no", sa.String(50)), sa.Column("seal_no", sa.String(50)), sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_loads_load_no", "loads", ["load_no"], unique=True); op.create_index("ix_loads_warehouse_id", "loads", ["warehouse_id"]); op.create_index("ix_loads_carrier_id", "loads", ["carrier_id"]); op.create_index("ix_loads_status", "loads", ["status"]); op.create_index("ix_loads_appointment_time", "loads", ["appointment_time"]); op.create_index("ix_loads_status_warehouse", "loads", ["status", "warehouse_id"]); op.create_index("ix_loads_created_by", "loads", ["created_by"])
    op.add_column("outbound_orders", sa.Column("load_id", sa.Integer(), sa.ForeignKey("loads.id", ondelete="SET NULL")))
    op.create_index("ix_outbound_orders_load_id", "outbound_orders", ["load_id"])

def downgrade():
    op.drop_index("ix_outbound_orders_load_id", table_name="outbound_orders"); op.drop_column("outbound_orders", "load_id")
    op.drop_table("loads"); op.execute("DROP TYPE IF EXISTS load_status")
