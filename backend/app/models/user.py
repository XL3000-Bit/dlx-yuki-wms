import enum
from sqlalchemy import Boolean, Enum, ForeignKey, String, Table, Column
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


user_warehouse_scopes = Table(
    "user_warehouse_scopes", Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("warehouse_id", ForeignKey("warehouses.id", ondelete="CASCADE"), primary_key=True),
)

user_customer_scopes = Table(
    "user_customer_scopes", Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("customer_id", ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    warehouse_scope_mode: Mapped[ScopeMode] = mapped_column(Enum(ScopeMode, name="scope_mode"), default=ScopeMode.ALL, server_default="ALL")
    customer_scope_mode: Mapped[ScopeMode] = mapped_column(Enum(ScopeMode, name="scope_mode", create_type=False), default=ScopeMode.ALL, server_default="ALL")
    warehouses: Mapped[list["Warehouse"]] = relationship(secondary=user_warehouse_scopes)
    customers: Mapped[list["Customer"]] = relationship(secondary=user_customer_scopes)

    @property
    def warehouse_ids(self) -> list[int]:
        return [item.id for item in self.warehouses]

    @property
    def customer_ids(self) -> list[int]:
        return [item.id for item in self.customers]

    @property
    def permissions(self) -> list[str]:
        from app.services.access_policy import permissions_for
        return permissions_for(self)
