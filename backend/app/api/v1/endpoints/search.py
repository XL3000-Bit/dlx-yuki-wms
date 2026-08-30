from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.services.global_search import search

router = APIRouter(prefix="/search", tags=["Global Search"])


@router.get("")
def global_search(db: DbSession, user: CurrentUser, q: str = Query(...), limit: int = Query(20, ge=1, le=50)):
    normalized = q.strip()
    if len(normalized) < 2:
        raise HTTPException(422, "Search query must contain at least 2 characters")
    return search(db, normalized, limit, user)
