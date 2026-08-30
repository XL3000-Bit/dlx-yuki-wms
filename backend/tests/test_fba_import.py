from datetime import date
from io import BytesIO
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.models import FBAInventoryAllocation,FBAShipment,ImportJob,InventoryLot
from app.imports.mapping import suggest_fba_mapping

def make_inventory(client,seed,container,pallet=5):
    payload={"container_number":container,"customer_id":seed["customer"].id,"warehouse_id":seed["warehouse"].id,"received_date":str(date.today()),"fc_code":"ONT8","pallet_qty":pallet,"carton_qty":50,"weight_lbs":5000,"cbm":20,"location_id":seed["location"].id,"status":3}
    inbound=client.post("/api/v1/inbound",json=payload).json();return client.post(f"/api/v1/inbound/{inbound['id']}/receive-to-inventory").json()
def workbook(rows):
    wb=Workbook();ws=wb.active;ws.append(["FBA No","Warehouse","Amazon FC","Container Number","Pallet Qty","Carton Qty","Weight LBS","CBM","ST#"])
    for row in rows:ws.append(row)
    stream=BytesIO();wb.save(stream);return stream.getvalue()
def test_fba_aliases():
    m=suggest_fba_mapping([" FBA Number ","Amazon FC","CNTR#","APT Time","ST#"]);assert m[" FBA Number "]=="fba_no";assert m["Amazon FC"]=="amazon_fc_code";assert m["CNTR#"]=="container_number";assert m["ST#"]=="st_number"
def test_fba_import_preview_grouping_confirm(client:TestClient,db:Session,seed):
    make_inventory(client,seed,"IMP-A");make_inventory(client,seed,"IMP-B")
    content=workbook([["FBA-EXCEL-1","DLX-LAX","ONT8","IMP-A",2,10,1000,4,"ST-IMP"],["FBA-EXCEL-1","DLX-LAX","ONT8","IMP-B",3,12,1200,5,"ST-IMP"]])
    preview=client.post("/api/v1/imports/fba/preview",files={"file":("fba.xlsx",content)});assert preview.status_code==201,preview.text;p=preview.json();assert p["suggested_mapping"]["Amazon FC"]=="amazon_fc_code"
    validation=client.post(f"/api/v1/imports/fba/{p['job_id']}/validate",json={"mapping":p["suggested_mapping"]});assert validation.status_code==200,validation.text;assert validation.json()["valid_rows"]==2
    result=client.post(f"/api/v1/imports/fba/{p['job_id']}/confirm",json={"mapping":p["suggested_mapping"]});assert result.status_code==200,result.text;assert result.json()["imported_rows"]==2
    db.expire_all();assert db.scalar(select(func.count()).select_from(FBAShipment))==1;assert db.scalar(select(func.count()).select_from(FBAInventoryAllocation))==2;assert db.scalar(select(func.sum(FBAInventoryAllocation.allocated_pallet_qty)))==5
def test_fba_import_unknown_inventory_and_overallocation(client:TestClient,seed):
    make_inventory(client,seed,"IMP-LIMIT",pallet=5);content=workbook([["FBA-ERR","DLX-LAX","ONT8","MISSING",1,0,0,0,""],["FBA-ERR","DLX-LAX","ONT8","IMP-LIMIT",6,0,0,0,""]]);p=client.post("/api/v1/imports/fba/preview",files={"file":("errors.xlsx",content)}).json();v=client.post(f"/api/v1/imports/fba/{p['job_id']}/validate",json={"mapping":p["suggested_mapping"]}).json();assert v["error_rows"]==2;codes={issue["code"]for row in v["rows"]for issue in row["issues"]};assert{"UNKNOWN_INVENTORY","OVER_ALLOCATION"}.issubset(codes)
def test_fba_import_transaction_rollback(client:TestClient,db:Session,seed,monkeypatch):
    make_inventory(client,seed,"ROLL-A");make_inventory(client,seed,"ROLL-B");content=workbook([["ROLL-FBA","DLX-LAX","ONT8","ROLL-A",1,0,0,0,""],["ROLL-FBA","DLX-LAX","ONT8","ROLL-B",1,0,0,0,""]]);p=client.post("/api/v1/imports/fba/preview",files={"file":("rollback.xlsx",content)}).json();import app.services.fba_import as service;original=service.allocate;calls=0
    def fail_second(*args,**kwargs):
        nonlocal calls;calls+=1
        if calls==2:raise RuntimeError("forced")
        return original(*args,**kwargs)
    monkeypatch.setattr(service,"allocate",fail_second)
    try:client.post(f"/api/v1/imports/fba/{p['job_id']}/confirm",json={"mapping":p["suggested_mapping"]})
    except RuntimeError:pass
    db.expire_all();assert db.scalar(select(func.count()).select_from(FBAShipment))==0;assert db.scalar(select(func.count()).select_from(FBAInventoryAllocation))==0;assert all(x.allocated_pallet_qty==0 for x in db.scalars(select(InventoryLot)).all());assert db.get(ImportJob,p["job_id"]).status.value=="FAILED"
