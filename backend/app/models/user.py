import enum
from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    WAREHOUSE = "WAREHOUSE"
    VIEWER = "VIEWER"


class ScopeMode(str, enum.Enum):
    ALL = "ALL"
    SELECTED = "SELECTED"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    warehouse_scope_mode: Mapped[ScopeMode] = mapped_column(
        Enum(ScopeMode, name="user_warehouse_scope_mode"), default=ScopeMode.ALL, server_default="ALL"
    )
    customer_scope_mode: Mapped[ScopeMode] = mapped_column(
        Enum(ScopeMode, name="user_customer_scope_mode"), default=ScopeMode.ALL, server_default="ALL"
    )
    warehouse_scopes: Mapped[list["UserWarehouseScope"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    customer_scopes: Mapped[list["UserCustomerScope"]] = relationship(back_populates="user", cascade="all, delete-orphan")
