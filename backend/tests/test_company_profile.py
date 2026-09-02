from pathlib import Path

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import company_profile as endpoint
from app.core.security import create_access_token
from app.models.company_profile import CompanyProfile
from app.models.inbound import AuditLog
from app.services import company_profile as service


URL = "/api/v1/company-profile"


def payload(**changes):
    values = {
        "company_name": "DLX Logistics",
        "brand_name": "Yuki WMS",
        "legal_name": "DLX Logistics LLC",
        "email": "ops@example.test",
        "phone": "555-0100",
        "address": "1 Warehouse Way",
        "city": "Los Angeles",
        "state": "CA",
        "zip_code": "90001",
        "country": "US",
        "timezone": "America/Los_Angeles",
        "default_warehouse_id": None,
    }
    values.update(changes)
    return values


def add_profile(db, **changes):
    row = CompanyProfile(singleton_key=1, **payload(**changes))
    db.add(row)
    db.commit()
    return row


def test_get_requires_authentication(client):
    client.headers.pop("Authorization")
    assert client.get(URL).status_code == 401


def test_get_zero_rows_is_404(client, db):
    response = client.get(URL)
    assert response.status_code == 404
    assert db.scalar(select(CompanyProfile)) is None


def test_get_existing_profile(client, db):
    row = add_profile(db)
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json()["id"] == row.id


def test_get_is_side_effect_free(client, db):
    add_profile(db)
    before = db.query(AuditLog).count()
    assert client.get(URL).status_code == 200
    assert db.query(AuditLog).count() == before


def test_put_requires_authentication(client):
    client.headers.pop("Authorization")
    assert client.put(URL, json=payload()).status_code == 401


def test_put_requires_admin(client, seed):
    viewer = seed["viewer"]
    client.headers["Authorization"] = f"Bearer {create_access_token(str(viewer.id))}"
    assert client.put(URL, json=payload()).status_code == 403


def test_put_creates_singleton(client, db):
    response = client.put(URL, json=payload())
    assert response.status_code == 200
    assert response.json()["company_name"] == "DLX Logistics"
    assert db.query(CompanyProfile).count() == 1


def test_create_writes_complete_audit(client, db, seed):
    response = client.put(URL, json=payload())
    audit = db.scalar(select(AuditLog).where(AuditLog.entity_type == "COMPANY_PROFILE"))
    assert audit.action == "CREATE"
    assert audit.user_id == seed["admin"].id
    assert audit.entity_id == response.json()["id"]
    assert audit.before_data is None
    assert audit.after_data["company_name"] == "DLX Logistics"


def test_second_put_updates_same_row(client, db):
    first_id = client.put(URL, json=payload()).json()["id"]
    second = client.put(URL, json=payload(phone="555-0200"))
    assert second.status_code == 200
    assert second.json()["id"] == first_id
    assert db.query(CompanyProfile).count() == 1


def test_update_audit_contains_only_changed_fields(client, db):
    add_profile(db)
    response = client.put(URL, json=payload(phone="555-0200"))
    assert response.status_code == 200
    audit = db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert audit.action == "UPDATE"
    assert audit.before_data == {"phone": "555-0100"}
    assert audit.after_data == {"phone": "555-0200"}


def test_noop_put_creates_no_audit(client, db):
    add_profile(db)
    assert client.put(URL, json=payload()).status_code == 200
    assert db.query(AuditLog).count() == 0


def test_invalid_payload_is_422(client):
    assert client.put(URL, json=payload(company_name="")).status_code == 422


def test_get_multiple_rows_returns_stable_conflict(client, monkeypatch):
    def fail(_db):
        raise service.CompanyProfileIntegrityError("Multiple company profiles exist")
    monkeypatch.setattr(endpoint, "get_company_profile", fail)
    response = client.get(URL)
    assert response.status_code == 409
    assert response.json()["detail"] == "Multiple company profiles exist"


def test_put_multiple_rows_returns_stable_conflict(client, monkeypatch):
    def fail(*_args):
        raise service.CompanyProfileIntegrityError("Multiple company profiles exist")
    monkeypatch.setattr(endpoint, "save_company_profile", fail)
    assert client.put(URL, json=payload()).status_code == 409


def test_integrity_race_returns_409(client, monkeypatch):
    def fail(*_args):
        raise service.CompanyProfileWriteConflict("Company profile singleton write conflict")
    monkeypatch.setattr(endpoint, "save_company_profile", fail)
    assert client.put(URL, json=payload()).status_code == 409


def test_audit_failure_rolls_back_profile_update(client, db, monkeypatch):
    row = add_profile(db)
    def fail(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(service, "write_audit", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.put(URL, json=payload(phone="555-9999"))
    db.expire_all()
    assert db.get(CompanyProfile, row.id).phone == "555-0100"


def test_model_declares_singleton_constraints():
    table = CompanyProfile.__table__
    names = {constraint.name for constraint in table.constraints}
    assert "uq_company_profiles_singleton_key" in names
    assert "ck_company_profiles_singleton_key_is_one" in names
    assert table.c.singleton_key.nullable is False


def test_migration_has_single_parent_and_duplicate_guard():
    path = Path(__file__).parents[1] / "alembic/versions/20260902_0026_company_profile_singleton.py"
    source = path.read_text(encoding="utf-8")
    assert 'down_revision = "20260902_0025"' in source
    assert "SELECT count(*) FROM company_profiles" in source
    assert "resolve duplicates" in source
    assert "DELETE FROM COMPANY_PROFILES" not in source.upper()
