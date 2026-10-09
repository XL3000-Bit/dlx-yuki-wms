"""phase 10.3 work order activity history"""
from alembic import op
import sqlalchemy as sa
revision='20260829_0015';down_revision='20260829_0014';branch_labels=None;depends_on=None
def upgrade():
 op.create_table('work_order_events',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('work_order_id',sa.Integer(),sa.ForeignKey('work_orders.id',ondelete='CASCADE'),nullable=False),sa.Column('event_type',sa.String(32),nullable=False),sa.Column('from_status',sa.String(24)),sa.Column('to_status',sa.String(24)),sa.Column('actor_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),sa.Column('assigned_to_before',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),sa.Column('assigned_to_after',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),sa.Column('assigned_team_before',sa.String(100)),sa.Column('assigned_team_after',sa.String(100)),sa.Column('priority_before',sa.String(16)),sa.Column('priority_after',sa.String(16)),sa.Column('note',sa.Text()),sa.Column('metadata_json',sa.JSON()),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
 for name,col in [('ix_work_order_events_work_order_id','work_order_id'),('ix_work_order_events_event_type','event_type'),('ix_work_order_events_actor_user_id','actor_user_id'),('ix_work_order_events_assigned_to_before','assigned_to_before'),('ix_work_order_events_assigned_to_after','assigned_to_after')]:op.create_index(name,'work_order_events',[col])
 op.create_index('ix_work_order_events_order_created','work_order_events',['work_order_id','created_at'])
def downgrade():op.drop_table('work_order_events')
