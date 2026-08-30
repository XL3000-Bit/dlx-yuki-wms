"""operational notification center

Revision ID: 20260830_0020
Revises: 20260830_0019
"""
from alembic import op
import sqlalchemy as sa
revision="20260830_0020"; down_revision="20260830_0019"; branch_labels=None; depends_on=None
def upgrade():
    nt=sa.Enum("EXCEPTION_CRITICAL","EXCEPTION_AGING","WORK_ORDER_URGENT","WORK_ORDER_OVERDUE","LOAD_APPOINTMENT_UPCOMING","POD_PENDING","CONTAINER_ALERT","SYSTEM",name="notification_type"); ns=sa.Enum("INFO","WARNING","HIGH","CRITICAL",name="notification_severity")
    nt.create(op.get_bind(),checkfirst=True); ns.create(op.get_bind(),checkfirst=True)
    op.create_table("operational_notifications",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("notification_type",nt,nullable=False),sa.Column("severity",ns,nullable=False),sa.Column("title",sa.String(200),nullable=False),sa.Column("message",sa.Text(),nullable=False),sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("warehouse_id",sa.Integer(),sa.ForeignKey("warehouses.id",ondelete="CASCADE")),sa.Column("source_type",sa.String(40),nullable=False),sa.Column("source_id",sa.Integer(),nullable=False),sa.Column("reference",sa.String(100),nullable=False),sa.Column("target_route",sa.String(200),nullable=False),sa.Column("dedupe_key",sa.String(180),nullable=False),sa.Column("is_read",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("read_at",sa.DateTime(timezone=True)),sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("resolved_at",sa.DateTime(timezone=True)),sa.Column("expires_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.UniqueConstraint("user_id","dedupe_key",name="uq_operational_notifications_user_dedupe"))
    for c in ("notification_type","severity","user_id","warehouse_id","source_type","source_id","is_read","is_active","expires_at"): op.create_index(f"ix_operational_notifications_{c}","operational_notifications",[c])
    op.create_index("ix_operational_notifications_user_unread_created","operational_notifications",["user_id","is_active","is_read","created_at"]); op.create_index("ix_operational_notifications_source","operational_notifications",["source_type","source_id","is_active"])
def downgrade():
    op.drop_table("operational_notifications"); sa.Enum(name="notification_severity").drop(op.get_bind(),checkfirst=True); sa.Enum(name="notification_type").drop(op.get_bind(),checkfirst=True)
