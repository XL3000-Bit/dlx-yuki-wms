from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from app.api.deps import CurrentUser, DbSession, require_admin
from app.models.company_profile import CompanyProfile
from app.models.user import User
from app.schemas.common import Timestamped
from app.services.company_profile import (
    CompanyProfileIntegrityError,
    CompanyProfileWriteConflict,
    get_company_profile,
    save_company_profile,
)

router = APIRouter(prefix="/company-profile", tags=["Company"])

class CompanyProfileInput(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    brand_name: str = Field(min_length=1, max_length=200)
    legal_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    state: str = "CA"
    zip_code: str = ""
    country: str = "US"
    timezone: str = "America/Los_Angeles"
    default_warehouse_id: int | None = None

class CompanyProfileRead(Timestamped, CompanyProfileInput):
    pass

@router.get("", response_model=CompanyProfileRead)
def read_profile(db: DbSession, _: CurrentUser) -> CompanyProfile:
    try:
        row = get_company_profile(db)
    except CompanyProfileIntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company profile not initialized")
    return row

@router.put("", response_model=CompanyProfileRead)
def save_profile(payload: CompanyProfileInput, db: DbSession, user: Annotated[User, Depends(require_admin)]) -> CompanyProfile:
    try:
        return save_company_profile(db, payload.model_dump(), user)
    except CompanyProfileIntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except CompanyProfileWriteConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
