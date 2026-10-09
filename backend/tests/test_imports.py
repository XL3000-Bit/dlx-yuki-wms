from io import BytesIO
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.models import ImportJob,InboundRecord
from app.imports.mapping import suggest_mapping

def xlsx(rows):
    wb=Workbook();ws=wb.active;ws.append(["CNTR#","Warehouse","FC","PLT","CTNS","Weight(LBS)","CBM","LOC","Received Date"])
    for row in rows:ws.append(row)
    stream=BytesIO();wb.save(stream);return stream.getvalue()
def test_alias_mapping():
    result=suggest_mapping([" CNTR# ","仓点","板数","箱数","重量","方数","库位","入库日期"]);assert result[" CNTR# "]=="container_number";assert result["仓点"]=="fc_code";assert result["库位"]=="location"
def test_preview_xlsx_validate_and_confirm(client:TestClient,db:Session,seed):
    content=xlsx([["MSCU1234567","DLX-LAX","LAX9",10,200,12000,42.5,"A01","2026-08-28"]]);preview=client.post("/api/v1/imports/inbound/preview",files={"file":("inbound.xlsx",content,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")});assert preview.status_code==201,preview.text;p=preview.json();assert p["total_rows"]==1;assert p["suggested_mapping"]["CNTR#"]=="container_number"
    valid=client.post(f"/api/v1/imports/inbound/{p['job_id']}/validate",json={"mapping":p["suggested_mapping"]});assert valid.status_code==200,valid.text;assert valid.json()["valid_rows"]==1
    confirmed=client.post(f"/api/v1/imports/inbound/{p['job_id']}/confirm",json={"mapping":p["suggested_mapping"],"duplicate_strategy":"SKIP"});assert confirmed.status_code==200,confirmed.text;assert confirmed.json()["imported_rows"]==1;row=db.scalar(select(InboundRecord));assert row is not None;assert row.import_job_id==p["job_id"]
    assert client.post(f"/api/v1/imports/inbound/{p['job_id']}/validate",json={"mapping":p["suggested_mapping"]}).status_code==409
    assert client.post(f"/api/v1/imports/inbound/{p['job_id']}/confirm",json={"mapping":p["suggested_mapping"],"duplicate_strategy":"SKIP"}).status_code==409
def test_preview_csv_invalid_values_and_unknown_masters(client:TestClient):
    csv=b"Container,Warehouse,Location,Pallet,Received Date\nC1,UNKNOWN,BAD,abc,not-a-date\n";preview=client.post("/api/v1/imports/inbound/preview",files={"file":("inbound.csv",csv,"text/csv")}).json();validated=client.post(f"/api/v1/imports/inbound/{preview['job_id']}/validate",json={"mapping":preview["suggested_mapping"]});assert validated.status_code==200;body=validated.json();assert body["error_rows"]==1;codes={x["code"] for x in body["rows"][0]["issues"]};assert{"UNKNOWN_WAREHOUSE","INVALID_NUMERIC","INVALID_DATE"}.issubset(codes)
def test_unknown_location_warning_and_duplicate_skip(client:TestClient):
    content=xlsx([["DUP1","DLX-LAX","LAX9",1,1,1,1,"UNKNOWN","2026-08-28"]]);p=client.post("/api/v1/imports/inbound/preview",files={"file":("one.xlsx",content)}).json();v=client.post(f"/api/v1/imports/inbound/{p['job_id']}/validate",json={"mapping":p["suggested_mapping"]}).json();assert v["warning_rows"]==1;assert v["error_rows"]==0;client.post(f"/api/v1/imports/inbound/{p['job_id']}/confirm",json={"mapping":p["suggested_mapping"],"duplicate_strategy":"SKIP"})
    p2=client.post("/api/v1/imports/inbound/preview",files={"file":("two.xlsx",content)}).json();result=client.post(f"/api/v1/imports/inbound/{p2['job_id']}/confirm",json={"mapping":p2["suggested_mapping"],"duplicate_strategy":"SKIP"}).json();assert result["skipped_rows"]==1;assert result["imported_rows"]==0
def test_mapping_duplicate_target_rejected(client:TestClient):
    csv=b"Container,Warehouse\nC1,DLX-LAX\n";p=client.post("/api/v1/imports/inbound/preview",files={"file":("x.csv",csv)}).json();r=client.post(f"/api/v1/imports/inbound/{p['job_id']}/validate",json={"mapping":{"Container":"container_number","Warehouse":"container_number"}});assert r.status_code==422
def test_confirm_transaction_rollback(client:TestClient,db:Session,monkeypatch):
    content=xlsx([["R1","DLX-LAX","LAX9",1,1,1,1,"A01","2026-08-28"],["R2","DLX-LAX","LAX9",1,1,1,1,"A01","2026-08-29"]]);p=client.post("/api/v1/imports/inbound/preview",files={"file":("rollback.xlsx",content)}).json();import app.services.import_service as service;original=service.create_inbound;calls=0
    def fail_second(*args,**kwargs):
        nonlocal calls;calls+=1
        if calls==2:raise RuntimeError("forced failure")
        return original(*args,**kwargs)
    monkeypatch.setattr(service,"create_inbound",fail_second)
    with pytest.raises(RuntimeError):client.post(f"/api/v1/imports/inbound/{p['job_id']}/confirm",json={"mapping":p["suggested_mapping"],"duplicate_strategy":"SKIP"})
    db.expire_all();assert db.scalar(select(func.count()).select_from(InboundRecord))==0;assert db.get(ImportJob,p["job_id"]).status.value=="FAILED"
