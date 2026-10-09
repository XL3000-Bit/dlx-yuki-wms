"""Durable partial shipment and POD history for UNI BOL."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20260917_0035'
down_revision = '20260917_0034'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('uni_fba_bols', sa.Column('workflow', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))

def downgrade():
    op.drop_column('uni_fba_bols', 'workflow')
