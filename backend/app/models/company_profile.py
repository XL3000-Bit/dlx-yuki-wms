from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class CompanyProfile(TimestampMixin, Base):
    __tablename__ = "company_profiles"
    __table_args__ = (
        CheckConstraint("singleton_key = 1", name="singleton_key_is_one"),
        UniqueConstraint("singleton_key", name="uq_company_profiles_singleton_key"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    singleton_key: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    company_name: Mapped[str] = mapped_column(String(200), default="DLX")
    brand_name: Mapped[str] = mapped_column(String(200), default="WMS")
    legal_name: Mapped[str] = mapped_column(String(200), default="DLX")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    state: Mapped[str] = mapped_column(String(50), default="CA")
    zip_code: Mapped[str] = mapped_column(String(20), default="")
    country: Mapped[str] = mapped_column(String(2), default="US")
    timezone: Mapped[str] = mapped_column(String(64), default="America/Los_Angeles")
    default_warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True)
