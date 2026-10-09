"""Link operational documents to inbound cargo."""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0032"
down_revision = "20260909_0031"
branch_labels = None
depends_on = None

OLD = "load_id IS NOT NULL OR outbound_id IS NOT NULL OR bol_id IS NOT NULL OR work_order_id IS NOT NULL OR operational_exception_id IS NOT NULL OR container_tracking_id IS NOT NULL"
CHECK = "ck_operational_documents_business_link_required"


def upgrade():
    op.add_column("operational_documents", sa.Column("inbound_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_operational_documents_inbound_id_inbound_records", "operational_documents", "inbound_records", ["inbound_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_operational_documents_inbound_id", "operational_documents", ["inbound_id"])
    # Revision 0019 passes this name through the metadata naming convention.
    op.drop_constraint(CHECK, "operational_documents", type_="check")
    op.create_check_constraint(CHECK, "operational_documents", "inbound_id IS NOT NULL OR " + OLD)


def downgrade():
    # Inbound-only documents must be relinked before downgrading; never delete them.
    op.drop_constraint(CHECK, "operational_documents", type_="check")
    op.create_check_constraint(CHECK, "operational_documents", OLD)
    op.drop_index("ix_operational_documents_inbound_id", table_name="operational_documents")
    op.drop_constraint("fk_operational_documents_inbound_id_inbound_records", "operational_documents", type_="foreignkey")
    op.drop_column("operational_documents", "inbound_id")
