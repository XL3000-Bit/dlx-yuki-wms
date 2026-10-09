from typing import Annotated
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    try: user_id = int(decode_token(token, "access")["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc: raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active: raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive or missing user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN: raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    return user


def require_warehouse_write(user: CurrentUser) -> User:
    if user.role not in {UserRole.ADMIN, UserRole.MANAGER, UserRole.INBOUND, UserRole.WAREHOUSE}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Warehouse write permission required")
    return user


def require_outbound_write(user: CurrentUser) -> User:
    if user.role not in {UserRole.ADMIN, UserRole.MANAGER, UserRole.OUTBOUND, UserRole.WAREHOUSE}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Outbound write permission required")
    return user
