from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class WorkOrderEvent(Base):
    __tablename__='work_order_events'
    id:Mapped[int]=mapped_column(primary_key=True)
    work_order_id:Mapped[int]=mapped_column(ForeignKey('work_orders.id',ondelete='CASCADE'),index=True)
    event_type:Mapped[str]=mapped_column(String(32),index=True)
    # legacy status transition fields
    from_status:Mapped[str|None]=mapped_column(String(24)); to_status:Mapped[str|None]=mapped_column(String(24))
    actor_user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id',ondelete='SET NULL'),index=True)
    assigned_to_before:Mapped[int|None]=mapped_column(ForeignKey('users.id',ondelete='SET NULL')); assigned_to_after:Mapped[int|None]=mapped_column(ForeignKey('users.id',ondelete='SET NULL'))
    assigned_team_before:Mapped[str|None]=mapped_column(String(100)); assigned_team_after:Mapped[str|None]=mapped_column(String(100))
    priority_before:Mapped[str|None]=mapped_column(String(16)); priority_after:Mapped[str|None]=mapped_column(String(16))
    note:Mapped[str|None]=mapped_column(Text)
    metadata_json:Mapped[dict|None]=mapped_column(JSON)
    # new authoritative fields
    field_name:Mapped[str|None]=mapped_column(String(64),index=True)
    old_value:Mapped[str|None]=mapped_column(Text)
    new_value:Mapped[str|None]=mapped_column(Text)
    message:Mapped[str|None]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    work_order=relationship('WorkOrder',back_populates='events'); actor=relationship('User',foreign_keys=[actor_user_id]); assigned_before=relationship('User',foreign_keys=[assigned_to_before]); assigned_after=relationship('User',foreign_keys=[assigned_to_after])
    __table_args__=(Index('ix_work_order_events_order_created','work_order_id','created_at'),)
