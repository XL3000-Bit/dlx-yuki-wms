from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password
from app.models.user import User
from app.schemas.user import TokenPair


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(or_(User.username == username, User.email == username)))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    return user


def issue_tokens(user_id: int) -> TokenPair:
    subject = str(user_id)
    return TokenPair(access_token=create_access_token(subject), refresh_token=create_refresh_token(subject))


def refresh_tokens(db: Session, token: str) -> TokenPair:
    try: user_id = int(decode_token(token, "refresh")["sub"])
    except Exception as exc: raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active: raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive or missing user")
    return issue_tokens(user.id)
