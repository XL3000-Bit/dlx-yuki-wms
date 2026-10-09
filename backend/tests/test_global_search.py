from fastapi.testclient import TestClient

from app.main import app
from app.models import BOL, ContainerTracking, FBAShipment, OutboundOrder, PickingList


def make_records(db, seed):
    common = dict(customer_id=seed["customer"].id, warehouse_id=seed["warehouse"].id, created_by=seed["admin"].id)
    fba = FBAShipment(fba_no="FBA-EXACT-100", amazon_fc_code="ONT8", status=1, st_number="ST-PREFIX-555", reference_no="CUSTOM-REF-77", **common)
    db.add(fba); db.flush()
    outbound = OutboundOrder(ob_no="OB-EXACT-200", status=2, reference_no="OB-EXACT-200", picking_reference="PICK-REF-88", **common)
    db.add(outbound); db.flush()
    container = ContainerTracking(container_number="MSCU1234567", mbl_number="MBL-PREFIX-9", customer_reference="CUSTOM-REF-77", delivery_warehouse_raw="DLX-LAX", source_fingerprint="search-container-1")
    picking = PickingList(picking_no="PICK-EXACT-300", outbound_order_id=outbound.id, status=0, created_by=seed["admin"].id)
    bol = BOL(bol_no="BOL-EXACT-400", outbound_order_id=outbound.id, fba_shipment_id=fba.id, customer_id=seed["customer"].id, warehouse_id=seed["warehouse"].id, ship_from_name="DLX", ship_from_address="1 Warehouse Way", status=0, created_by=seed["admin"].id)
    db.add_all([container, picking, bol]); db.commit()
    return {"fba": fba, "outbound": outbound, "container": container, "picking": picking, "bol": bol}


def flattened(payload):
    return [item for group in payload["groups"] for item in group["items"]]


def test_exact_match_is_ranked_first(client, db, seed):
    make_records(db, seed)
    data = client.get("/api/v1/search", params={"q": "ob-exact-200"}).json()
    assert data["total"] == 1
    assert data["groups"][0]["type"] == "OUTBOUND"
    assert data["groups"][0]["items"][0]["match_rank"] == 1


def test_prefix_match(client, db, seed):
    make_records(db, seed)
    item = flattened(client.get("/api/v1/search", params={"q": "st-prefix"}).json())[0]
    assert item["type"] == "FBA" and item["match_rank"] == 2


def test_contains_match(client, db, seed):
    make_records(db, seed)
    item = flattened(client.get("/api/v1/search", params={"q": "12345"}).json())[0]
    assert item["type"] == "CONTAINER" and item["match_rank"] == 3


def test_empty_and_whitespace_queries_rejected(client):
    assert client.get("/api/v1/search", params={"q": ""}).status_code == 422
    assert client.get("/api/v1/search", params={"q": "   "}).status_code == 422


def test_result_limit_and_duplicate_prevention(client, db, seed):
    make_records(db, seed)
    data = client.get("/api/v1/search", params={"q": "exact", "limit": 2}).json()
    assert data["total"] == 2
    outbound = client.get("/api/v1/search", params={"q": "ob-exact-200"}).json()
    assert len([x for x in flattened(outbound) if x["type"] == "OUTBOUND"]) == 1


def test_unknown_reference(client, db, seed):
    make_records(db, seed)
    assert client.get("/api/v1/search", params={"q": "DOES-NOT-EXIST"}).json() == {"query": "DOES-NOT-EXIST", "total": 0, "groups": []}


def test_authentication_required():
    assert TestClient(app).get("/api/v1/search", params={"q": "OB"}).status_code == 401


def test_cross_model_grouped_response(client, db, seed):
    make_records(db, seed)
    data = client.get("/api/v1/search", params={"q": "custom-ref-77"}).json()
    assert {group["type"] for group in data["groups"]} == {"CONTAINER", "FBA"}
    assert all(group["count"] == len(group["items"]) for group in data["groups"])
