from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile
from app.models.user import User
from app.services.audit import write_audit


PROFILE_FIELDS = (
    "company_name", "brand_name", "legal_name", "email", "phone", "address",
    "city", "state", "zip_code", "country", "timezone", "default_warehouse_id",
)


class CompanyProfileIntegrityError(RuntimeError):
    pass


class CompanyProfileWriteConflict(RuntimeError):
    pass


def snapshot(row: CompanyProfile) -> dict[str, Any]:
    return {key: getattr(row, key) for key in PROFILE_FIELDS}


def get_company_profile(db: Session) -> CompanyProfile | None:
    rows = db.scalars(select(CompanyProfile).order_by(CompanyProfile.id).limit(2)).all()
    if len(rows) > 1:
        raise CompanyProfileIntegrityError("Multiple company profiles exist")
    return rows[0] if rows else None


def save_company_profile(db: Session, values: dict[str, Any], user: User) -> CompanyProfile:
    row = get_company_profile(db)
    try:
        if row is None:
            row = CompanyProfile(singleton_key=1, **values)
            db.add(row)
            db.flush()
            write_audit(db, user, "CREATE", "COMPANY_PROFILE", row.id, None, snapshot(row))
        else:
            before: dict[str, Any] = {}
            after: dict[str, Any] = {}
            for key, value in values.items():
                old_value = getattr(row, key)
                if old_value != value:
                    before[key] = old_value
                    after[key] = value
                    setattr(row, key, value)
            if not after:
                return row
            write_audit(db, user, "UPDATE", "COMPANY_PROFILE", row.id, before, after)
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise CompanyProfileWriteConflict("Company profile singleton write conflict") from exc
    except Exception:
        db.rollback()
        raise
