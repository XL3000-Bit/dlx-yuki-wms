import enum
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

class NotificationType(str, enum.Enum):
    EXCEPTION_CRITICAL="EXCEPTION_CRITICAL"; EXCEPTION_AGING="EXCEPTION_AGING"; WORK_ORDER_URGENT="WORK_ORDER_URGENT"; WORK_ORDER_OVERDUE="WORK_ORDER_OVERDUE"; LOAD_APPOINTMENT_UPCOMING="LOAD_APPOINTMENT_UPCOMING"; POD_PENDING="POD_PENDING"; CONTAINER_ALERT="CONTAINER_ALERT"; SYSTEM="SYSTEM"
class NotificationSeverity(str, enum.Enum): INFO="INFO"; WARNING="WARNING"; HIGH="HIGH"; CRITICAL="CRITICAL"

class OperationalNotification(TimestampMixin, Base):
    __tablename__="operational_notifications"
    id:Mapped[int]=mapped_column(primary_key=True)
    notification_type:Mapped[NotificationType]=mapped_column(Enum(NotificationType,name="notification_type"),index=True)
    severity:Mapped[NotificationSeverity]=mapped_column(Enum(NotificationSeverity,name="notification_severity"),index=True)
    title:Mapped[str]=mapped_column(String(200)); message:Mapped[str]=mapped_column(Text)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    warehouse_id:Mapped[int|None]=mapped_column(ForeignKey("warehouses.id",ondelete="CASCADE"),index=True)
    source_type:Mapped[str]=mapped_column(String(40),index=True); source_id:Mapped[int]=mapped_column(index=True)
    reference:Mapped[str]=mapped_column(String(100)); target_route:Mapped[str]=mapped_column(String(200)); dedupe_key:Mapped[str]=mapped_column(String(180))
    is_read:Mapped[bool]=mapped_column(Boolean,default=False,server_default="false",index=True); read_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    is_active:Mapped[bool]=mapped_column(Boolean,default=True,server_default="true",index=True); resolved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),index=True)
    user=relationship("User"); warehouse=relationship("Warehouse")
    __table_args__=(UniqueConstraint("user_id","dedupe_key",name="uq_operational_notifications_user_dedupe"),Index("ix_operational_notifications_user_unread_created","user_id","is_active","is_read","created_at"),Index("ix_operational_notifications_source","source_type","source_id","is_active"))
