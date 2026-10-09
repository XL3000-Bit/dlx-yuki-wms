"""Allow maintaining outbound transfer codes independently of redirects."""
from alembic import op
import sqlalchemy as sa

revision = '20260909_0029'
down_revision = '20260909_0028'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('outbound_orders', sa.Column('transfer_code', sa.String(100), nullable=True))

def downgrade():
    op.drop_column('outbound_orders', 'transfer_code')
