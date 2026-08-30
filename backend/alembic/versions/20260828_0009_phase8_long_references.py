"""phase 8 long real-world PO and FBA reference lists

Revision ID: 20260828_0009
Revises: 20260828_0008
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260828_0009"
down_revision: Union[str, None] = "20260828_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_inbound_records_po_number", table_name="inbound_records")
    op.drop_index("ix_inbound_records_fba_reference", table_name="inbound_records")
    op.alter_column("inbound_records", "po_number", existing_type=sa.String(200), type_=sa.Text())
    op.alter_column("inbound_records", "fba_reference", existing_type=sa.String(200), type_=sa.Text())


def downgrade() -> None:
    op.alter_column("inbound_records", "fba_reference", existing_type=sa.Text(), type_=sa.String(200))
    op.alter_column("inbound_records", "po_number", existing_type=sa.Text(), type_=sa.String(200))
    op.create_index("ix_inbound_records_fba_reference", "inbound_records", ["fba_reference"])
    op.create_index("ix_inbound_records_po_number", "inbound_records", ["po_number"])
