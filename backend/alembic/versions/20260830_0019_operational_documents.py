"""operational documents and document events

Revision ID: 20260830_0019
Revises: 20260830_0018
"""
from alembic import op
import sqlalchemy as sa

revision = "20260830_0019"
down_revision = "20260830_0018"
branch_labels = None
depends_on = None


def upgrade():
    document_type = sa.Enum("BOL", "POD", "DELIVERY_RECEIPT", "WAREHOUSE", "EXCEPTION_ATTACHMENT", "GENERAL", name="operational_document_type")
    document_status = sa.Enum("DRAFT", "AVAILABLE", "SUPERSEDED", "ARCHIVED", "PENDING", "RECEIVED", name="operational_document_status")
    document_type.create(op.get_bind(), checkfirst=True)
    document_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "operational_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_no", sa.String(32), nullable=False),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column("status", document_status, nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("original_file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("load_id", sa.Integer(), sa.ForeignKey("loads.id", ondelete="SET NULL")),
        sa.Column("outbound_id", sa.Integer(), sa.ForeignKey("outbound_orders.id", ondelete="SET NULL")),
        sa.Column("bol_id", sa.Integer(), sa.ForeignKey("bols.id", ondelete="SET NULL")),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="SET NULL")),
        sa.Column("exception_id", sa.Integer(), sa.ForeignKey("operational_exceptions.id", ondelete="SET NULL")),
        sa.Column("container_tracking_id", sa.Integer(), sa.ForeignKey("container_trackings.id", ondelete="SET NULL")),
        sa.Column("description", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_no", name="uq_operational_documents_document_no"),
    )
    op.create_index("ix_operational_documents_document_no", "operational_documents", ["document_no"])
    op.create_index("ix_operational_documents_document_type", "operational_documents", ["document_type"])
    op.create_index("ix_operational_documents_status", "operational_documents", ["status"])
    op.create_index("ix_operational_documents_warehouse_id", "operational_documents", ["warehouse_id"])
    op.create_index("ix_operational_documents_load_id", "operational_documents", ["load_id"])
    op.create_index("ix_operational_documents_outbound_id", "operational_documents", ["outbound_id"])
    op.create_index("ix_operational_documents_bol_id", "operational_documents", ["bol_id"])
    op.create_index("ix_operational_documents_uploaded_at", "operational_documents", ["uploaded_at"])
    op.create_index("ix_operational_documents_type_status", "operational_documents", ["document_type", "status"])
    op.create_table(
        "document_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("operational_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_events_document_id", "document_events", ["document_id"])
    op.create_index("ix_document_events_timeline", "document_events", ["document_id", "created_at", "id"])


def downgrade():
    op.drop_table("document_events")
    op.drop_table("operational_documents")
    sa.Enum(name="operational_document_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="operational_document_type").drop(op.get_bind(), checkfirst=True)
