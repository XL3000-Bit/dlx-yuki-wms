from pydantic import BaseModel, Field
from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from app.api.deps import CurrentUser, DbSession, require_admin
from app.models.company_profile import CompanyProfile
from app.models.user import User
from app.schemas.common import Timestamped
from app.services.audit import write_audit

router = APIRouter(prefix="/company-profile", tags=["Company"])

PROFILE_FIELDS = (
    "company_name", "brand_name", "legal_name", "email", "phone", "address",
    "city", "state", "zip_code", "country", "timezone", "default_warehouse_id",
)

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

def _snapshot(row: CompanyProfile) -> dict:
    return {key: getattr(row, key) for key in PROFILE_FIELDS}

def _get_or_create(db: DbSession) -> CompanyProfile:
    row = db.scalar(select(CompanyProfile).order_by(CompanyProfile.id).limit(1))
    if row:
        return row
    row = CompanyProfile(
        company_name="DLX",
        brand_name="Yuki WMS",
        legal_name="DLX",
        timezone="America/Los_Angeles",
        country="US",
        state="CA",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.get("", response_model=CompanyProfileRead)
def read_profile(db: DbSession, _: CurrentUser) -> CompanyProfile:
    try:
        return _get_or_create(db)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Company profile table is missing. Run alembic upgrade head.",
        ) from exc

@router.put("", response_model=CompanyProfileRead)
def save_profile(payload: CompanyProfileInput, db: DbSession, user: Annotated[User, Depends(require_admin)]) -> CompanyProfile:
    row = _get_or_create(db)
    before = _snapshot(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    write_audit(db, user, "UPDATE", "COMPANY_PROFILE", row.id, before, _snapshot(row))
    db.commit()
    db.refresh(row)
    return row
