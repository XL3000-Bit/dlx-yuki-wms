"""phase 8 outbound PO list length

Revision ID: 20260828_0010
Revises: 20260828_0009
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260828_0010"
down_revision: Union[str, None] = "20260828_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.drop_index("ix_outbound_orders_po_number", table_name="outbound_orders")
    op.alter_column("outbound_orders", "po_number", existing_type=sa.String(100), type_=sa.Text())

def downgrade() -> None:
    op.alter_column("outbound_orders", "po_number", existing_type=sa.Text(), type_=sa.String(100))
    op.create_index("ix_outbound_orders_po_number", "outbound_orders", ["po_number"])
