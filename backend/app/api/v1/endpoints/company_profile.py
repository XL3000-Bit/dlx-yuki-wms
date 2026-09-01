from pydantic import BaseModel, Field
from sqlalchemy import select
from fastapi import APIRouter, Depends
from typing import Annotated
from app.api.deps import CurrentUser, DbSession, require_admin
from app.models.company_profile import CompanyProfile
from app.models.user import User
from app.schemas.common import Timestamped

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
    id: int

def _ensure_table(db: DbSession) -> None:
    CompanyProfile.__table__.create(bind=db.get_bind(), checkfirst=True)

def _get_or_create(db: DbSession) -> CompanyProfile:
    _ensure_table(db)
    row = db.scalar(select(CompanyProfile).order_by(CompanyProfile.id).limit(1))
    if row: return row
    row = CompanyProfile(company_name="DLX", brand_name="Yuki WMS", legal_name="DLX", timezone="America/Los_Angeles", country="US", state="CA")
    db.add(row); db.commit(); db.refresh(row); return row

@router.get("", response_model=CompanyProfileRead)
def read_profile(db: DbSession, _: CurrentUser) -> CompanyProfile:
    return _get_or_create(db)

@router.put("", response_model=CompanyProfileRead)
def save_profile(payload: CompanyProfileInput, db: DbSession, _: Annotated[User, Depends(require_admin)]) -> CompanyProfile:
    row = _get_or_create(db)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit(); db.refresh(row); return row
