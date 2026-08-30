from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, or_, select
from app.api.deps import CurrentUser, DbSession, require_admin
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.user_scope import UserCustomerScope, UserWarehouseScope
from app.models.customer import Customer
from app.models.warehouse import Warehouse
from app.schemas.user import UserCreateInput, UserRead, UserScopeUpdate
from app.services.access import get_access_scope, scope_payload

router = APIRouter(prefix="/users", tags=["Users"])


def read_user(db, user: User) -> UserRead:
    scope = get_access_scope(db, user)
    payload = scope_payload(scope)
    return UserRead.model_validate(user).model_copy(update=payload)


def _create(payload: UserCreateInput, db: DbSession) -> User:
    exists = db.scalar(select(User.id).where(or_(User.username == payload.username, User.email == payload.email)))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already exists")
    user = User(username=payload.username, display_name=payload.display_name, email=payload.email, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user); db.commit(); db.refresh(user); return user


@router.post("/bootstrap", response_model=UserRead, status_code=201)
def bootstrap(payload: UserCreateInput, db: DbSession) -> UserRead:
    if db.scalar(select(func.count()).select_from(User)) != 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bootstrap is already complete")
    payload.role = UserRole.ADMIN
    return read_user(db, _create(payload, db))


@router.post("", response_model=UserRead, status_code=201)
def create_user(payload: UserCreateInput, db: DbSession, _: Annotated[User, Depends(require_admin)]) -> UserRead:
    return read_user(db, _create(payload, db))


@router.get("", response_model=list[UserRead])
def list_users(db: DbSession, _: Annotated[User, Depends(require_admin)]) -> list[UserRead]:
    return [read_user(db, row) for row in db.scalars(select(User).order_by(User.id.desc())).all()]


@router.get("/me", response_model=UserRead)
def me(db: DbSession, user: CurrentUser) -> UserRead:
    return read_user(db, user)


@router.patch("/{user_id}/scope", response_model=UserRead)
def update_scope(user_id: int, payload: UserScopeUpdate, db: DbSession, _: Annotated[User, Depends(require_admin)]) -> UserRead:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if payload.warehouse_ids and db.scalar(select(func.count()).select_from(Warehouse).where(Warehouse.id.in_(payload.warehouse_ids))) != len(set(payload.warehouse_ids)):
        raise HTTPException(422, "Warehouse not found")
    if payload.customer_ids and db.scalar(select(func.count()).select_from(Customer).where(Customer.id.in_(payload.customer_ids))) != len(set(payload.customer_ids)):
        raise HTTPException(422, "Customer not found")
    user.warehouse_scope_mode = payload.warehouse_scope_mode
    user.customer_scope_mode = payload.customer_scope_mode
    db.execute(delete(UserWarehouseScope).where(UserWarehouseScope.user_id == user.id))
    db.execute(delete(UserCustomerScope).where(UserCustomerScope.user_id == user.id))
    for warehouse_id in set(payload.warehouse_ids):
        db.add(UserWarehouseScope(user_id=user.id, warehouse_id=warehouse_id))
    for customer_id in set(payload.customer_ids):
        db.add(UserCustomerScope(user_id=user.id, customer_id=customer_id))
    db.commit(); db.refresh(user)
    return read_user(db, user)
