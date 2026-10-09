"""operational document and POD center

Revision ID: 20260830_0019
Revises: 20260830_0018
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260830_0019"; down_revision = "20260830_0018"; branch_labels = None; depends_on = None


def upgrade():
    dtype = postgresql.ENUM("BOL", "POD", "DELIVERY_RECEIPT", "WAREHOUSE", "EXCEPTION_ATTACHMENT", "GENERAL", name="operational_document_type", create_type=False)
    dstatus = postgresql.ENUM("DRAFT", "AVAILABLE", "SUPERSEDED", "ARCHIVED", name="operational_document_status", create_type=False)
    dtype.create(op.get_bind(), checkfirst=True); dstatus.create(op.get_bind(), checkfirst=True)
    op.create_table("operational_documents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("document_no", sa.String(40), nullable=False),
        sa.Column("document_type", dtype, nullable=False), sa.Column("status", dstatus, nullable=False, server_default="DRAFT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False), sa.Column("file_size", sa.BigInteger()), sa.Column("storage_key", sa.String(255)),
        sa.Column("checksum_sha256", sa.String(64)), sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("title", sa.String(200)), sa.Column("notes", sa.Text()),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="RESTRICT")),
        sa.Column("load_id", sa.Integer(), sa.ForeignKey("loads.id", ondelete="SET NULL")),
        sa.Column("outbound_id", sa.Integer(), sa.ForeignKey("outbound_orders.id", ondelete="SET NULL")),
        sa.Column("bol_id", sa.Integer(), sa.ForeignKey("bols.id", ondelete="SET NULL")),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="SET NULL")),
        sa.Column("operational_exception_id", sa.Integer(), sa.ForeignKey("operational_exceptions.id", ondelete="SET NULL")),
        sa.Column("container_tracking_id", sa.Integer(), sa.ForeignKey("container_trackings.id", ondelete="SET NULL")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)), sa.Column("archived_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_operational_documents_version_positive"),
        sa.CheckConstraint("load_id IS NOT NULL OR outbound_id IS NOT NULL OR bol_id IS NOT NULL OR work_order_id IS NOT NULL OR operational_exception_id IS NOT NULL OR container_tracking_id IS NOT NULL", name="ck_operational_documents_business_link_required"),
        sa.UniqueConstraint("document_no"), sa.UniqueConstraint("storage_key"))
    for col in ("document_no", "document_type", "status", "warehouse_id", "customer_id", "load_id", "outbound_id", "bol_id", "work_order_id", "operational_exception_id", "container_tracking_id", "created_by"):
        op.create_index(f"ix_operational_documents_{col}", "operational_documents", [col])
    op.create_index("ix_operational_documents_original_filename", "operational_documents", ["original_filename"])
    op.create_index("ix_operational_documents_scope_status", "operational_documents", ["warehouse_id", "status", "document_type"])
    op.create_table("document_events", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("operational_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("message", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_document_events_document_id", "document_events", ["document_id"]); op.create_index("ix_document_events_event_type", "document_events", ["event_type"])
    op.create_index("ix_document_events_actor_user_id", "document_events", ["actor_user_id"]); op.create_index("ix_document_events_created_at", "document_events", ["created_at"])
    op.create_index("ix_document_events_timeline", "document_events", ["document_id", "created_at", "id"])


def downgrade():
    op.drop_table("document_events"); op.drop_table("operational_documents")
    sa.Enum(name="operational_document_status").drop(op.get_bind(), checkfirst=True); sa.Enum(name="operational_document_type").drop(op.get_bind(), checkfirst=True)
