from fastapi import APIRouter
from app.api.deps import DbSession
from app.schemas.user import LoginRequest, RefreshRequest, TokenPair
from app.services.auth import authenticate, issue_tokens, refresh_tokens

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: DbSession) -> TokenPair: return issue_tokens(authenticate(db, payload.username, payload.password).id)

@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair: return refresh_tokens(db, payload.refresh_token)
