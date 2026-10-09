from enum import Enum

from fastapi import HTTPException, status
from sqlalchemy import false

from app.models.user import ScopeMode, User, UserRole


class Permission(str, Enum):
    READ = "read"
    MANAGE_INBOUND = "manage_inbound"
    MANAGE_OUTBOUND = "manage_outbound"
    MANAGE_WAREHOUSE = "manage_warehouse"
    MANAGE_USERS = "manage_users"


ROLE_PERMISSIONS = {
    UserRole.ADMIN: set(Permission),
    UserRole.MANAGER: {Permission.READ, Permission.MANAGE_INBOUND, Permission.MANAGE_OUTBOUND, Permission.MANAGE_WAREHOUSE},
    UserRole.INBOUND: {Permission.READ, Permission.MANAGE_INBOUND, Permission.MANAGE_WAREHOUSE},
    UserRole.OUTBOUND: {Permission.READ, Permission.MANAGE_OUTBOUND},
    UserRole.WAREHOUSE: {Permission.READ, Permission.MANAGE_INBOUND, Permission.MANAGE_OUTBOUND, Permission.MANAGE_WAREHOUSE},
    UserRole.VIEWER: {Permission.READ},
}


def permissions_for(user: User) -> list[str]:
    return sorted(permission.value for permission in ROLE_PERMISSIONS[user.role])


def warehouse_ids(user: User) -> set[int]:
    return {item.id for item in user.warehouses}


def customer_ids(user: User) -> set[int]:
    return {item.id for item in user.customers}


def warehouse_clause(user: User, column):
    if user.role == UserRole.ADMIN or user.warehouse_scope_mode == ScopeMode.ALL:
        return None
    ids = warehouse_ids(user)
    return column.in_(ids) if ids else false()


def customer_clause(user: User, column):
    if user.role == UserRole.ADMIN or user.customer_scope_mode == ScopeMode.ALL:
        return None
    ids = customer_ids(user)
    return column.in_(ids) if ids else false()


def scoped_statement(stmt, user: User, *, warehouse_column=None, customer_column=None):
    for clause in (warehouse_clause(user, warehouse_column) if warehouse_column is not None else None,
                   customer_clause(user, customer_column) if customer_column is not None else None):
        if clause is not None:
            stmt = stmt.where(clause)
    return stmt


def assert_warehouse_access(user: User, value: int | None) -> None:
    if value is not None and user.role != UserRole.ADMIN and user.warehouse_scope_mode == ScopeMode.SELECTED and value not in warehouse_ids(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Warehouse is outside your assigned scope")


def assert_customer_access(user: User, value: int | None) -> None:
    if value is not None and user.role != UserRole.ADMIN and user.customer_scope_mode == ScopeMode.SELECTED and value not in customer_ids(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Customer is outside your assigned scope")
