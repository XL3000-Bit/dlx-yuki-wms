from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from app.api.deps import CurrentUser, DbSession, require_admin
from app.core.security import hash_password
from app.models import Customer, Warehouse
from app.models.user import User, UserRole
from app.schemas.user import UserCreateInput, UserRead, UserScopeUpdate

router = APIRouter(prefix="/users", tags=["Users"])

def _create(payload: UserCreateInput, db: DbSession) -> User:
    exists = db.scalar(select(User.id).where(or_(User.username == payload.username, User.email == payload.email)))
    if exists: raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already exists")
    data = payload.model_dump(exclude={"password", "warehouse_ids", "customer_ids"})
    user = User(**data, password_hash=hash_password(payload.password))
    _set_scopes(user, payload.warehouse_ids, payload.customer_ids, db)
    db.add(user); db.commit(); db.refresh(user); return user


def _set_scopes(user: User, warehouse_ids: list[int], customer_ids: list[int], db: DbSession) -> None:
    warehouses = list(db.scalars(select(Warehouse).where(Warehouse.id.in_(set(warehouse_ids)))).all()) if warehouse_ids else []
    customers = list(db.scalars(select(Customer).where(Customer.id.in_(set(customer_ids)))).all()) if customer_ids else []
    if len(warehouses) != len(set(warehouse_ids)) or len(customers) != len(set(customer_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown warehouse or customer scope id")
    user.warehouses = warehouses
    user.customers = customers

@router.post("/bootstrap", response_model=UserRead, status_code=201)
def bootstrap(payload: UserCreateInput, db: DbSession) -> User:
    if db.scalar(select(func.count()).select_from(User)) != 0: raise HTTPException(status.HTTP_409_CONFLICT, "Bootstrap is already complete")
    payload.role = UserRole.ADMIN
    return _create(payload, db)

@router.post("", response_model=UserRead, status_code=201)
def create_user(payload: UserCreateInput, db: DbSession, _: Annotated[User, Depends(require_admin)]) -> User: return _create(payload, db)

@router.get("", response_model=list[UserRead])
def list_users(db: DbSession, _: Annotated[User, Depends(require_admin)]) -> list[User]: return list(db.scalars(select(User).order_by(User.id.desc())).all())

@router.patch("/{user_id}/scope", response_model=UserRead)
def update_scope(user_id: int, payload: UserScopeUpdate, db: DbSession, _: Annotated[User, Depends(require_admin)]) -> User:
    user = db.get(User, user_id)
    if user is None: raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.warehouse_scope_mode = payload.warehouse_scope_mode
    user.customer_scope_mode = payload.customer_scope_mode
    _set_scopes(user, payload.warehouse_ids, payload.customer_ids, db)
    db.commit(); db.refresh(user); return user

@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User: return user
