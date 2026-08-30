from datetime import date,timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.models import InventoryLot,InventoryTransaction,Warehouse,WarehouseArea,WarehouseLocation

def inbound_payload(seed,status=3,container="INV-CNTR-1",received=None):return{"container_number":container,"customer_id":seed["customer"].id,"warehouse_id":seed["warehouse"].id,"unload_date":str(date.today()-timedelta(days=24)),"received_date":str(received or date.today()-timedelta(days=22)),"fc_code":"ONT8","marking":"INV-MARK","pallet_qty":5,"carton_qty":50,"weight_lbs":5000,"cbm":20,"location_id":seed["location"].id,"status":status,"remark":"inventory test"}
def receive(client,seed,**kwargs):
    ib=client.post("/api/v1/inbound",json=inbound_payload(seed,**kwargs));assert ib.status_code==201,ib.text;r=client.post(f"/api/v1/inbound/{ib.json()['id']}/receive-to-inventory");assert r.status_code==200,r.text;return ib.json(),r.json()
def test_receive_inbound_to_inventory_and_prevent_duplicate(client:TestClient,db:Session,seed):
    inbound,lot=receive(client,seed);assert lot["lot_no"].startswith(f"LOT{date.today():%y%m%d}");assert lot["available_pallet_qty"]=="5.00";assert lot["source_inbound_id"]==inbound["id"]
    assert client.post(f"/api/v1/inbound/{inbound['id']}/receive-to-inventory").status_code==409;tx=db.scalar(select(InventoryTransaction));assert tx.transaction_type.value=="INBOUND";assert tx.reference_id==inbound["id"]
    refreshed=client.get(f"/api/v1/inbound/{inbound['id']}").json();assert refreshed["inventory_created"]is True;assert refreshed["inventory_lot_id"]==lot["id"]
def test_reject_invalid_inbound_status(client:TestClient,seed):
    inbound=client.post("/api/v1/inbound",json=inbound_payload(seed,status=2)).json();assert client.post(f"/api/v1/inbound/{inbound['id']}/receive-to-inventory").status_code==409
def test_inventory_list_search_filters_aging_priority_and_export(client:TestClient,seed):
    _,lot=receive(client,seed);result=client.get("/api/v1/inventory",params={"q":"INV-CNTR","fc_code":"ONT8","warehouse_id":seed["warehouse"].id,"location_id":seed["location"].id,"priority_level":"RED","aging_min":22,"has_available":True});assert result.status_code==200;body=result.json();assert body["meta"]["total"]==1;assert body["data"][0]["aging_days"]>=22;assert body["data"][0]["priority_label"]=="Process First"
    assert client.get("/api/v1/inventory/files/export.xlsx",params={"q":"INV-CNTR"}).content.startswith(b"PK")
def test_move_and_reject_cross_warehouse(client:TestClient,db:Session,seed):
    _,lot=receive(client,seed);area=db.scalar(select(WarehouseArea));new=WarehouseLocation(warehouse_id=seed["warehouse"].id,area_id=area.id,location_code="A02",location_name="A02");other_wh=Warehouse(warehouse_code="OTHER",warehouse_name="Other",address="2 Way",city="LA",state="CA",zip_code="90002");db.add_all([new,other_wh]);db.flush();other_area=WarehouseArea(warehouse_id=other_wh.id,area_code="STORAGE",area_name="Storage");db.add(other_area);db.flush();other=WarehouseLocation(warehouse_id=other_wh.id,area_id=other_area.id,location_code="B01",location_name="B01");db.add(other);db.commit()
    moved=client.post(f"/api/v1/inventory/{lot['id']}/move",json={"to_location_id":new.id,"remark":"rack move"});assert moved.status_code==200;assert moved.json()["location"]["code"]=="A02";assert client.get(f"/api/v1/inventory/{lot['id']}/transactions").json()[0]["transaction_type"]=="MOVE";assert client.post(f"/api/v1/inventory/{lot['id']}/move",json={"to_location_id":other.id}).status_code==422
def test_positive_negative_adjustment_and_prevent_negative(client:TestClient,db:Session,seed):
    _,lot=receive(client,seed);url=f"/api/v1/inventory/{lot['id']}/adjust";assert client.post(url,json={"pallet_delta":-6,"carton_delta":0,"weight_delta":0,"cbm_delta":0,"reason":"LOST"}).status_code==409;plus=client.post(url,json={"pallet_delta":2,"carton_delta":0,"weight_delta":0,"cbm_delta":0,"reason":"FOUND","remark":"count"});assert plus.status_code==200,plus.text;assert plus.json()["available_pallet_qty"]=="7.00"
    minus=client.post(url,json={"pallet_delta":-1,"carton_delta":0,"weight_delta":0,"cbm_delta":0,"reason":"COUNT_CORRECTION"});assert minus.status_code==200;assert minus.json()["available_pallet_qty"]=="6.00"
    critical=client.post(url,json={"pallet_delta":-7,"carton_delta":0,"weight_delta":0,"cbm_delta":0,"reason":"LOST"});assert critical.status_code==409;db.expire_all();assert db.get(InventoryLot,lot["id"]).available_pallet_qty==6
def test_hold_release_and_limits(client:TestClient,db:Session,seed):
    _,lot=receive(client,seed);base=f"/api/v1/inventory/{lot['id']}";assert client.post(f"{base}/hold",json={"pallet_qty":6,"carton_qty":0}).status_code==409
    held=client.post(f"{base}/hold",json={"pallet_qty":2,"carton_qty":10,"remark":"inspection"});assert held.status_code==200;assert held.json()["available_pallet_qty"]=="3.00";assert held.json()["hold_pallet_qty"]=="2.00";assert client.post(f"{base}/release",json={"pallet_qty":3,"carton_qty":0}).status_code==409
    released=client.post(f"{base}/release",json={"pallet_qty":1,"carton_qty":5,"remark":"passed"});assert released.status_code==200;assert released.json()["available_pallet_qty"]=="4.00";assert released.json()["hold_pallet_qty"]=="1.00"
    history=client.get(f"{base}/transactions");assert history.status_code==200;assert [x["transaction_type"]for x in history.json()]==["RELEASE","HOLD","INBOUND"]
def test_operation_transaction_rollback(client:TestClient,db:Session,seed,monkeypatch):
    _,lot=receive(client,seed);import app.services.inventory as service
    def fail(*_args,**_kwargs):raise RuntimeError("forced transaction failure")
    monkeypatch.setattr(service,"_tx",fail)
    with pytest.raises(RuntimeError):client.post(f"/api/v1/inventory/{lot['id']}/hold",json={"pallet_qty":1,"carton_qty":0})
    db.rollback();db.expire_all();stored=db.get(InventoryLot,lot["id"]);assert stored.available_pallet_qty==5;assert stored.hold_pallet_qty==0;assert db.scalar(select(func.count()).select_from(InventoryTransaction))==1
