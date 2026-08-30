from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.models import InboundRecord

def payload(seed):return{"container_number":"MSCU1234567","customer_id":seed["customer"].id,"warehouse_id":seed["warehouse"].id,"unload_date":"2026-08-27","received_date":"2026-08-28","fc_code":"LAX9","marking":"MK-1","pallet_qty":10,"carton_qty":200,"weight_lbs":12000.5,"cbm":42.25,"location_id":seed["location"].id,"status":2,"remark":"received"}
def test_create_list_filter_update_and_number(client:TestClient,seed):
    first=client.post("/api/v1/inbound",json=payload(seed));assert first.status_code==201,first.text;body=first.json();assert body["inbound_no"].startswith(f"IB{date.today():%y%m%d}");assert body["status_name"]=="Received";assert isinstance(body["aging_days"],int)
    second=client.post("/api/v1/inbound",json={**payload(seed),"container_number":"TGHU7894561"});assert second.status_code==201;assert int(second.json()["inbound_no"][-4:])==int(body["inbound_no"][-4:])+1
    listed=client.get("/api/v1/inbound",params={"q":"MSCU","warehouse_id":seed["warehouse"].id,"fc_code":"LAX9"}).json();assert listed["meta"]["total"]==1;assert listed["data"][0]["container_number"]=="MSCU1234567"
    updated=client.put(f"/api/v1/inbound/{body['id']}",json={**payload(seed),"remark":"updated","status":3});assert updated.status_code==200;assert updated.json()["remark"]=="updated";assert updated.json()["inbound_no"]==body["inbound_no"]
def test_negative_quantity_rejected(client:TestClient,seed):assert client.post("/api/v1/inbound",json={**payload(seed),"pallet_qty":-1}).status_code==422
def test_delete_requires_admin(client:TestClient,db:Session,seed):
    record=client.post("/api/v1/inbound",json=payload(seed)).json();client.headers["Authorization"]=f"Bearer {create_access_token(str(seed['viewer'].id))}";assert client.delete(f"/api/v1/inbound/{record['id']}").status_code==403;client.headers["Authorization"]=f"Bearer {create_access_token(str(seed['admin'].id))}";assert client.delete(f"/api/v1/inbound/{record['id']}").status_code==200;assert db.scalar(select(InboundRecord).where(InboundRecord.id==record["id"])) is None
def test_viewer_cannot_create_and_files_routes_work(client:TestClient,seed):
    template=client.get("/api/v1/inbound/files/template.xlsx");assert template.status_code==200;assert template.content.startswith(b"PK")
    export=client.get("/api/v1/inbound/files/export.xlsx");assert export.status_code==200;assert export.content.startswith(b"PK")
    client.headers["Authorization"]=f"Bearer {create_access_token(str(seed['viewer'].id))}";assert client.post("/api/v1/inbound",json=payload(seed)).status_code==403
