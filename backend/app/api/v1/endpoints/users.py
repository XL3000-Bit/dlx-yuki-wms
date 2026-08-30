from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from app.api.deps import CurrentUser, DbSession, require_admin
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreateInput, UserRead

router = APIRouter(prefix="/users", tags=["Users"])

def _create(payload: UserCreateInput, db: DbSession) -> User:
    exists = db.scalar(select(User.id).where(or_(User.username == payload.username, User.email == payload.email)))
    if exists: raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already exists")
    user = User(username=payload.username, display_name=payload.display_name, email=payload.email, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user); db.commit(); db.refresh(user); return user

@router.post("/bootstrap", response_model=UserRead, status_code=201)
def bootstrap(payload: UserCreateInput, db: DbSession) -> User:
    if db.scalar(select(func.count()).select_from(User)) != 0: raise HTTPException(status.HTTP_409_CONFLICT, "Bootstrap is already complete")
    payload.role = UserRole.ADMIN
    return _create(payload, db)

@router.post("", response_model=UserRead, status_code=201)
def create_user(payload: UserCreateInput, db: DbSession, _: Annotated[User, Depends(require_admin)]) -> User: return _create(payload, db)

@router.get("", response_model=list[UserRead])
def list_users(db: DbSession, _: Annotated[User, Depends(require_admin)]) -> list[User]: return list(db.scalars(select(User).order_by(User.id.desc())).all())

@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User: return user
