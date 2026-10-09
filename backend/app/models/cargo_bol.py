"""Permanent cargo identities, independent of outbound shipping documents."""
from sqlalchemy import CheckConstraint, ForeignKey, event, select
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class CargoBOL(TimestampMixin, Base):
    __tablename__ = "cargo_bols"
    __table_args__ = (CheckConstraint(
        "(CASE WHEN inbound_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN fba_shipment_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN history_outbound_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
        name="exactly_one_source",
    ),)

    id: Mapped[int] = mapped_column(primary_key=True)
    inbound_id: Mapped[int | None] = mapped_column(ForeignKey("inbound_records.id", ondelete="CASCADE"), unique=True)
    fba_shipment_id: Mapped[int | None] = mapped_column(ForeignKey("fba_shipments.id", ondelete="CASCADE"), unique=True)
    history_outbound_id: Mapped[int | None] = mapped_column(ForeignKey("outbound_orders.id", ondelete="CASCADE"), unique=True)
    inbound = relationship("InboundRecord")
    fba_shipment = relationship("FBAShipment")
    history_outbound = relationship("OutboundOrder")

    @property
    def bol_no(self) -> str:
        return f"BOL{self.id:012d}"

    @property
    def source(self):
        return self.inbound or self.fba_shipment or self.history_outbound


def register_cargo_bol_events():
    from app.models.inbound import InboundRecord
    from app.models.fba import FBAShipment
    from app.models.outbound import OutboundOrder
    from app.models import ImportJob

    def create_identity(mapper, connection, target):
        if isinstance(target, InboundRecord):
            source_key = "inbound_id"
        elif isinstance(target, FBAShipment):
            source_key = "fba_shipment_id"
        else:
            if not target.import_job_id or connection.scalar(select(ImportJob.profile_code).where(
                ImportJob.id == target.import_job_id
            )) != "WEST_COAST_4_0_HISTORY":
                return
            source_key = "history_outbound_id"
        connection.execute(CargoBOL.__table__.insert().values(**{source_key: target.id}))

    for model in (InboundRecord, FBAShipment, OutboundOrder):
        event.listen(model, "after_insert", create_identity)
