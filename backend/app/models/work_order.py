import enum
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

class WorkOrderType(str, enum.Enum): PICK='PICK'; STAGE='STAGE'; LOAD='LOAD'; CHECK='CHECK'; GENERAL='GENERAL'
class WorkOrderStatus(str, enum.Enum): OPEN='OPEN'; ASSIGNED='ASSIGNED'; IN_PROGRESS='IN_PROGRESS'; COMPLETED='COMPLETED'; CANCELED='CANCELED'
class WorkOrderPriority(str, enum.Enum): LOW='LOW'; NORMAL='NORMAL'; HIGH='HIGH'; URGENT='URGENT'

class WorkOrder(TimestampMixin, Base):
    __tablename__='work_orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    work_order_type: Mapped[WorkOrderType] = mapped_column(Enum(WorkOrderType, name='work_order_type'), index=True)
    status: Mapped[WorkOrderStatus] = mapped_column(Enum(WorkOrderStatus, name='work_order_status'), default=WorkOrderStatus.OPEN, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey('warehouses.id', ondelete='RESTRICT'), index=True)
    load_id: Mapped[int|None] = mapped_column(ForeignKey('loads.id', ondelete='SET NULL'), index=True)
    outbound_id: Mapped[int|None] = mapped_column(ForeignKey('outbound_orders.id', ondelete='SET NULL'), index=True)
    picking_list_id: Mapped[int|None] = mapped_column(ForeignKey('picking_lists.id', ondelete='SET NULL'), index=True)
    container_tracking_id: Mapped[int|None] = mapped_column(ForeignKey('container_trackings.id', ondelete='SET NULL'), index=True)
    operational_exception_id: Mapped[int|None] = mapped_column(ForeignKey('operational_exceptions.id', ondelete='SET NULL'), index=True)
    priority: Mapped[WorkOrderPriority] = mapped_column(Enum(WorkOrderPriority, name='work_order_priority'), default=WorkOrderPriority.NORMAL, index=True)
    assigned_to: Mapped[int|None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    assigned_team: Mapped[str|None] = mapped_column(String(100))
    scheduled_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str|None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), index=True)
    warehouse=relationship('Warehouse'); load=relationship('Load', back_populates='work_orders'); outbound=relationship('OutboundOrder', back_populates='work_orders'); picking_list=relationship('PickingList'); container_tracking=relationship('ContainerTracking'); assignee=relationship('User', foreign_keys=[assigned_to]); creator=relationship('User', foreign_keys=[created_by])
    operational_exception=relationship('OperationalException', back_populates='work_orders')
    events=relationship('WorkOrderEvent', back_populates='work_order', cascade='all, delete-orphan', order_by='WorkOrderEvent.created_at.desc()')
    __table_args__=(Index('ix_work_orders_warehouse_status','warehouse_id','status'),)
