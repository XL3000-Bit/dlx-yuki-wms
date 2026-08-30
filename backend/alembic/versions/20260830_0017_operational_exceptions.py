"""operational exception center foundation

Revision ID: 20260830_0017
Revises: 20260830_0016
"""
from alembic import op
import sqlalchemy as sa

revision = "20260830_0017"; down_revision = "20260830_0016"; branch_labels = None; depends_on = None


def upgrade():
    exception_type = sa.Enum("INVENTORY", "PICKING", "OUTBOUND", "CONTAINER", "DOCUMENT", "APPOINTMENT", "WAREHOUSE", "DATA", "OTHER", name="operational_exception_type")
    severity = sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="operational_exception_severity")
    status = sa.Enum("OPEN", "INVESTIGATING", "RESOLVED", "CANCELED", name="operational_exception_status")
    op.create_table("operational_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("exception_no", sa.String(32), nullable=False),
        sa.Column("exception_type", exception_type, nullable=False), sa.Column("severity", severity, nullable=False), sa.Column("status", status, nullable=False),
        sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("outbound_id", sa.Integer(), sa.ForeignKey("outbound_orders.id", ondelete="SET NULL")),
        sa.Column("load_id", sa.Integer(), sa.ForeignKey("loads.id", ondelete="SET NULL")),
        sa.Column("container_tracking_id", sa.Integer(), sa.ForeignKey("container_trackings.id", ondelete="SET NULL")),
        sa.Column("picking_list_id", sa.Integer(), sa.ForeignKey("picking_lists.id", ondelete="SET NULL")),
        sa.Column("bol_id", sa.Integer(), sa.ForeignKey("bols.id", ondelete="SET NULL")),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("assigned_team", sa.String(100)),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False), sa.Column("reported_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)), sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolution", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("exception_no"))
    for column in ("exception_no", "exception_type", "severity", "status", "warehouse_id", "outbound_id", "load_id", "container_tracking_id", "picking_list_id", "bol_id", "assigned_to", "assigned_team", "reported_at", "reported_by", "resolved_at"):
        op.create_index(f"ix_operational_exceptions_{column}", "operational_exceptions", [column])
    op.create_index("ix_operational_exceptions_scope", "operational_exceptions", ["warehouse_id", "status", "severity"])
    op.create_table("operational_exception_events", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operational_exception_id", sa.Integer(), sa.ForeignKey("operational_exceptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("field_name", sa.String(50)), sa.Column("old_value", sa.Text()), sa.Column("new_value", sa.Text()), sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_operational_exception_events_operational_exception_id", "operational_exception_events", ["operational_exception_id"])
    op.create_index("ix_operational_exception_events_event_type", "operational_exception_events", ["event_type"])
    op.create_index("ix_operational_exception_events_actor_user_id", "operational_exception_events", ["actor_user_id"])
    op.create_index("ix_operational_exception_events_created_at", "operational_exception_events", ["created_at"])
    op.create_index("ix_operational_exception_events_timeline", "operational_exception_events", ["operational_exception_id", "created_at", "id"])
    op.add_column("work_orders", sa.Column("operational_exception_id", sa.Integer(), sa.ForeignKey("operational_exceptions.id", ondelete="SET NULL")))
    op.create_index("ix_work_orders_operational_exception_id", "work_orders", ["operational_exception_id"])


def downgrade():
    op.drop_index("ix_work_orders_operational_exception_id", table_name="work_orders"); op.drop_column("work_orders", "operational_exception_id")
    op.drop_table("operational_exception_events"); op.drop_table("operational_exceptions")
    sa.Enum(name="operational_exception_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="operational_exception_severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="operational_exception_type").drop(op.get_bind(), checkfirst=True)
