from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class UserWarehouseScope(Base):
    __tablename__ = "user_warehouse_scopes"
    __table_args__ = (UniqueConstraint("user_id", "warehouse_id", name="uq_user_warehouse_scope"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="CASCADE"), index=True)
    user = relationship("User", back_populates="warehouse_scopes")
    warehouse = relationship("Warehouse")


class UserCustomerScope(Base):
    __tablename__ = "user_customer_scopes"
    __table_args__ = (UniqueConstraint("user_id", "customer_id", name="uq_user_customer_scope"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    user = relationship("User", back_populates="customer_scopes")
    customer = relationship("Customer")
