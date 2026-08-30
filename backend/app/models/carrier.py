from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Carrier(TimestampMixin, Base):
    __tablename__ = "carriers"
    id: Mapped[int] = mapped_column(primary_key=True)
    carrier_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    carrier_name: Mapped[str] = mapped_column(String(200), index=True)
    scac: Mapped[str | None] = mapped_column(String(10), unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    remark: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
