"""add generic work order event audit fields

Revision ID: 20260830_0016
Revises: 20260829_0015
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = '20260830_0016'
down_revision = '20260829_0015'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'work_order_events',
        sa.Column('field_name', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'work_order_events',
        sa.Column('old_value', sa.Text(), nullable=True),
    )
    op.add_column(
        'work_order_events',
        sa.Column('new_value', sa.Text(), nullable=True),
    )
    op.add_column(
        'work_order_events',
        sa.Column('message', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column('work_order_events', 'message')
    op.drop_column('work_order_events', 'new_value')
    op.drop_column('work_order_events', 'old_value')
    op.drop_column('work_order_events', 'field_name')
