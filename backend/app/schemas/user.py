from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole
from app.schemas.common import Timestamped


class UserCreateInput(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: UserRole = UserRole.VIEWER


class UserRead(Timestamped):
    username: str
    display_name: str
    email: EmailStr
    role: UserRole
    is_active: bool


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
