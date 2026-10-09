from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class AmazonFCAddress(TimestampMixin, Base):
    __tablename__ = "amazon_fc_addresses"
    id: Mapped[int] = mapped_column(primary_key=True)
    fc_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    fc_name: Mapped[str | None] = mapped_column(String(200))
    address_line1: Mapped[str] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(50))
    zip_code: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2), default="US", server_default="US")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
