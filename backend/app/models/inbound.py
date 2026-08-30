import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

JsonType=JSON().with_variant(JSONB(),"postgresql")
class InboundStatus(enum.IntEnum): PENDING=0; UNLOADING=1; RECEIVED=2; PUT_AWAY=3; COMPLETED=4; HOLD=5

class InboundRecord(TimestampMixin,Base):
    __tablename__="inbound_records";__table_args__=(CheckConstraint("pallet_qty >= 0",name="pallet_non_negative"),CheckConstraint("carton_qty >= 0",name="carton_non_negative"),CheckConstraint("weight_lbs IS NULL OR weight_lbs >= 0",name="weight_non_negative"),CheckConstraint("cbm IS NULL OR cbm >= 0",name="cbm_non_negative"),CheckConstraint("status BETWEEN 0 AND 5",name="status_range"))
    id:Mapped[int]=mapped_column(primary_key=True);inbound_no:Mapped[str]=mapped_column(String(20),unique=True,index=True);container_number:Mapped[str]=mapped_column(String(50),index=True);customer_id:Mapped[int|None]=mapped_column(ForeignKey("customers.id",ondelete="RESTRICT"),index=True);warehouse_id:Mapped[int]=mapped_column(ForeignKey("warehouses.id",ondelete="RESTRICT"),index=True);unload_date:Mapped[date|None]=mapped_column(Date);received_date:Mapped[date|None]=mapped_column(Date);fc_code:Mapped[str|None]=mapped_column(String(20),index=True);marking:Mapped[str|None]=mapped_column(String(100),index=True);pallet_qty:Mapped[Decimal]=mapped_column(Numeric(12,2),default=0);carton_qty:Mapped[Decimal]=mapped_column(Numeric(12,2),default=0);weight_lbs:Mapped[Decimal|None]=mapped_column(Numeric(14,2));cbm:Mapped[Decimal|None]=mapped_column(Numeric(14,4));location_id:Mapped[int|None]=mapped_column(ForeignKey("warehouse_locations.id",ondelete="RESTRICT"),index=True);raw_location_text:Mapped[str|None]=mapped_column(Text);po_number:Mapped[str|None]=mapped_column(Text);fba_reference:Mapped[str|None]=mapped_column(Text);weight_source:Mapped[str|None]=mapped_column(String(32));source_metadata:Mapped[dict[str,Any]|None]=mapped_column(JsonType);import_row_id:Mapped[int|None]=mapped_column(ForeignKey("import_rows.id",ondelete="SET NULL"),index=True);status:Mapped[int]=mapped_column(SmallInteger,default=0,index=True);remark:Mapped[str|None]=mapped_column(Text);import_job_id:Mapped[int|None]=mapped_column(ForeignKey("import_jobs.id",ondelete="SET NULL"),index=True);created_by:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="RESTRICT"),index=True)
    customer=relationship("Customer");warehouse=relationship("Warehouse");location=relationship("WarehouseLocation");creator=relationship("User");import_job=relationship("ImportJob")
    inventory_lot=relationship("InventoryLot",back_populates="source_inbound",uselist=False)

class AuditLog(Base):
    __tablename__="audit_logs"
    id:Mapped[int]=mapped_column(primary_key=True);user_id:Mapped[int|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),index=True);action:Mapped[str]=mapped_column(String(30),index=True);entity_type:Mapped[str]=mapped_column(String(50),index=True);entity_id:Mapped[int|None]=mapped_column(Integer,index=True);before_data:Mapped[dict[str,Any]|None]=mapped_column(JsonType);after_data:Mapped[dict[str,Any]|None]=mapped_column(JsonType);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

