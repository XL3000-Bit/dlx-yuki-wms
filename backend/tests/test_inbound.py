from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.models import InboundRecord, InventoryLot

def payload(seed):return{"container_number":"MSCU1234567","customer_id":seed["customer"].id,"warehouse_id":seed["warehouse"].id,"unload_date":"2026-08-27","received_date":"2026-08-28","fc_code":"LAX9","marking":"MK-1","pallet_qty":10,"carton_qty":200,"weight_lbs":12000.5,"cbm":42.25,"location_id":seed["location"].id,"status":2,"remark":"received"}
def test_create_list_filter_update_and_number(client:TestClient,seed):
    first=client.post("/api/v1/inbound",json=payload(seed));assert first.status_code==201,first.text;body=first.json();assert body["inbound_no"].startswith(f"IB{date.today():%y%m%d}");assert body["status_name"]=="Received";assert isinstance(body["aging_days"],int)
    second=client.post("/api/v1/inbound",json={**payload(seed),"container_number":"TGHU7894561"});assert second.status_code==201;assert int(second.json()["inbound_no"][-4:])==int(body["inbound_no"][-4:])+1
    listed=client.get("/api/v1/inbound",params={"q":"MSCU","warehouse_id":seed["warehouse"].id,"fc_code":"LAX9"}).json();assert listed["meta"]["total"]==1;assert listed["data"][0]["container_number"]=="MSCU1234567"
    updated=client.put(f"/api/v1/inbound/{body['id']}",json={**payload(seed),"remark":"updated","status":3});assert updated.status_code==200;assert updated.json()["remark"]=="updated";assert updated.json()["inbound_no"]==body["inbound_no"]

def test_po_number_create_edit_list_receive_and_cancel(client:TestClient,db:Session,seed):
    created=client.post("/api/v1/inbound",json={**payload(seed),"container_number":"PO-CNTR-001","received_date":None,"status":0,"po_number":"PO-TRIAL-001","remark":"separate remark"})
    assert created.status_code==201,created.text
    record=created.json();assert record["po_number"]=="PO-TRIAL-001";assert record["remark"]=="separate remark"
    detail=client.get(f"/api/v1/inbound/{record['id']}");assert detail.status_code==200;assert detail.json()["po_number"]=="PO-TRIAL-001"
    listed=client.get("/api/v1/inbound",params={"q":"PO-TRIAL-001"}).json();assert listed["meta"]["total"]==1;assert listed["data"][0]["po_number"]=="PO-TRIAL-001"
    edited=client.patch(f"/api/v1/inbound/{record['id']}",json={"po_number":"PO-TRIAL-002"});assert edited.status_code==200,edited.text;assert edited.json()["po_number"]=="PO-TRIAL-002";assert edited.json()["remark"]=="separate remark"
    received=client.post(f"/api/v1/inbound/{record['id']}/receive");assert received.status_code==200,received.text
    assert client.get(f"/api/v1/inbound/{record['id']}").json()["po_number"]=="PO-TRIAL-002"

    canceled=client.post("/api/v1/inbound",json={**payload(seed),"container_number":"PO-CNTR-002","received_date":None,"status":0,"po_number":"PO-CANCEL-001"}).json()
    response=client.post(f"/api/v1/inbound/{canceled['id']}/cancel");assert response.status_code==200,response.text;assert response.json()["po_number"]=="PO-CANCEL-001";assert response.json()["status"]==6
    assert db.scalar(select(InventoryLot).where(InventoryLot.source_inbound_id==canceled["id"])) is None
def test_negative_quantity_rejected(client:TestClient,seed):assert client.post("/api/v1/inbound",json={**payload(seed),"pallet_qty":-1}).status_code==422
def test_delete_requires_admin(client:TestClient,db:Session,seed):
    record=client.post("/api/v1/inbound",json=payload(seed)).json();client.headers["Authorization"]=f"Bearer {create_access_token(str(seed['viewer'].id))}";assert client.delete(f"/api/v1/inbound/{record['id']}").status_code==403;client.headers["Authorization"]=f"Bearer {create_access_token(str(seed['admin'].id))}";assert client.delete(f"/api/v1/inbound/{record['id']}").status_code==200;assert db.scalar(select(InboundRecord).where(InboundRecord.id==record["id"])) is None
def test_viewer_cannot_create_and_files_routes_work(client:TestClient,seed):
    template=client.get("/api/v1/inbound/files/template.xlsx");assert template.status_code==200;assert template.content.startswith(b"PK")
    export=client.get("/api/v1/inbound/files/export.xlsx");assert export.status_code==200;assert export.content.startswith(b"PK")
    client.headers["Authorization"]=f"Bearer {create_access_token(str(seed['viewer'].id))}";assert client.post("/api/v1/inbound",json=payload(seed)).status_code==403
