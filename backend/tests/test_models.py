from app.db.base import Base
import app.models  # noqa: F401

def test_phase1_tables_are_registered() -> None:
    expected = {"users", "customers", "warehouses", "warehouse_areas", "warehouse_locations", "carriers", "amazon_fc_addresses"}
    assert expected.issubset(set(Base.metadata.tables))

def test_location_relations_and_uniqueness() -> None:
    table = Base.metadata.tables["warehouse_locations"]
    targets = {fk.target_fullname for fk in table.foreign_keys}
    assert targets == {"warehouses.id", "warehouse_areas.id"}
    assert any({"warehouse_id", "location_code"} == {column.name for column in constraint.columns} for constraint in table.constraints if hasattr(constraint, "columns"))

def test_password_hash_is_not_a_plain_password_field() -> None:
    columns = Base.metadata.tables["users"].columns
    assert "password_hash" in columns
    assert "password" not in columns
