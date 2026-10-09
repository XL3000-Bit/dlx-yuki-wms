from sqlalchemy import ForeignKey, String, CheckConstraint, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin

JsonType = JSON().with_variant(JSONB(), "postgresql")


class UniBol(TimestampMixin, Base):
    """UNI business workflow, separate from the generated shipping document."""
    __tablename__ = 'uni_fba_bols'
    __table_args__ = (CheckConstraint("status IN ('Pre','Confirmed','In Transit','Delivered','Exception','Canceled')", name='uni_bol_status'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fba_shipment_id: Mapped[int] = mapped_column(ForeignKey('fba_shipments.id'), unique=True)
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey('outbound_orders.id'), unique=True)
    # Dispatch may group several BOLs; stock ownership remains per BOL.
    dispatch_ob_no: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), default='Pre')
    version: Mapped[int] = mapped_column(default=1)
    details: Mapped[dict] = mapped_column(JsonType, default=dict)
    workflow: Mapped[dict] = mapped_column(JsonType, default=dict, server_default='{}')
