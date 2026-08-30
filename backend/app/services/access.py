from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy import select
from app.models.user import ScopeMode, User, UserRole
from app.models.user_scope import UserCustomerScope, UserWarehouseScope


@dataclass(frozen=True)
class AccessScope:
    warehouse_all: bool
    warehouse_ids: frozenset[int]
    customer_all: bool
    customer_ids: frozenset[int]

    def allows_warehouse(self, warehouse_id: int | None) -> bool:
        if self.warehouse_all:
            return True
        if warehouse_id is None:
            return False
        return warehouse_id in self.warehouse_ids

    def allows_customer(self, customer_id: int | None) -> bool:
        if self.customer_all:
            return True
        if customer_id is None:
            return True
        return customer_id in self.customer_ids


def get_access_scope(db, user: User) -> AccessScope:
    if user.role == UserRole.ADMIN or user.warehouse_scope_mode == ScopeMode.ALL:
        warehouse_all = True
        warehouse_ids: frozenset[int] = frozenset()
    else:
        warehouse_all = False
        warehouse_ids = frozenset(
            db.scalars(select(UserWarehouseScope.warehouse_id).where(UserWarehouseScope.user_id == user.id)).all()
        )
    if user.role == UserRole.ADMIN or user.customer_scope_mode == ScopeMode.ALL:
        customer_all = True
        customer_ids: frozenset[int] = frozenset()
    else:
        customer_all = False
        customer_ids = frozenset(
            db.scalars(select(UserCustomerScope.customer_id).where(UserCustomerScope.user_id == user.id)).all()
        )
    return AccessScope(warehouse_all, warehouse_ids, customer_all, customer_ids)


def apply_warehouse_scope(stmt, column, scope: AccessScope):
    if scope.warehouse_all:
        return stmt
    if not scope.warehouse_ids:
        return stmt.where(column.in_((-1,)))
    return stmt.where(column.in_(scope.warehouse_ids))


def apply_customer_scope(stmt, column, scope: AccessScope):
    if scope.customer_all:
        return stmt
    if not scope.customer_ids:
        return stmt.where(column.is_(None))
    return stmt.where((column.is_(None)) | column.in_(scope.customer_ids))


def ensure_warehouse_visible(scope: AccessScope, warehouse_id: int | None, *, detail: str = "Not found") -> None:
    if not scope.allows_warehouse(warehouse_id):
        raise HTTPException(404, detail)


def ensure_warehouse_writable(scope: AccessScope, warehouse_id: int | None, *, detail: str = "Not found") -> None:
    ensure_warehouse_visible(scope, warehouse_id, detail=detail)


def scope_payload(scope: AccessScope) -> dict:
    return {
        "warehouse_scope_mode": "ALL" if scope.warehouse_all else "SELECTED",
        "warehouse_ids": sorted(scope.warehouse_ids),
        "customer_scope_mode": "ALL" if scope.customer_all else "SELECTED",
        "customer_ids": sorted(scope.customer_ids),
    }
