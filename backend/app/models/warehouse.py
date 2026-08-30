from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Warehouse(TimestampMixin, Base):
    __tablename__ = "warehouses"
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    warehouse_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(50))
    zip_code: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2), default="US", server_default="US")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    areas: Mapped[list["WarehouseArea"]] = relationship(back_populates="warehouse", cascade="all, delete-orphan")
    locations: Mapped[list["WarehouseLocation"]] = relationship(back_populates="warehouse", cascade="all, delete-orphan")


class WarehouseArea(TimestampMixin, Base):
    __tablename__ = "warehouse_areas"
    __table_args__ = (UniqueConstraint("warehouse_id", "area_code", name="uq_warehouse_area_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="CASCADE"), index=True)
    area_code: Mapped[str] = mapped_column(String(50))
    area_name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    warehouse: Mapped[Warehouse] = relationship(back_populates="areas")
    locations: Mapped[list["WarehouseLocation"]] = relationship(back_populates="area")


class WarehouseLocation(TimestampMixin, Base):
    __tablename__ = "warehouse_locations"
    __table_args__ = (UniqueConstraint("warehouse_id", "location_code", name="uq_warehouse_location_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="CASCADE"), index=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("warehouse_areas.id", ondelete="RESTRICT"), index=True)
    location_code: Mapped[str] = mapped_column(String(50), index=True)
    location_name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    warehouse: Mapped[Warehouse] = relationship(back_populates="locations")
    area: Mapped[WarehouseArea] = relationship(back_populates="locations")
