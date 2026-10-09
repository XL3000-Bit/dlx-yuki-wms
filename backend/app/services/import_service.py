from datetime import UTC,date,datetime
from decimal import Decimal,InvalidOperation
from typing import Any
from fastapi import HTTPException
from sqlalchemy import delete,func,or_,select
from sqlalchemy.orm import Session
from app.imports.mapping import validate_mapping
from app.models import AuditLog,Customer,ImportError,ImportJob,ImportRow,InboundRecord,Warehouse,WarehouseLocation
from app.models.import_job import ImportSeverity,ImportStatus,RowValidationStatus
from app.models.inbound import InboundStatus
from app.schemas.imports import ImportSummary,ValidationSummary
from app.schemas.inbound import InboundCreate
from app.services.inbound import create_inbound

SYSTEM_FIELDS={"container_number","customer","warehouse","unload_date","received_date","fc_code","marking","pallet_qty","carton_qty","weight_lbs","cbm","location","remark"}
def _date(v:Any)->date|None:
    if v in (None,""):return None
    if isinstance(v,date):return v
    text=str(v).strip()
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%m/%d/%y","%Y/%m/%d"):
        try:return datetime.strptime(text,fmt).date()
        except ValueError:pass
    raise ValueError("Invalid date")
def _decimal(v:Any)->Decimal|None:
    if v in (None,""):return None
    try:value=Decimal(str(v).replace(",","").strip())
    except InvalidOperation as exc:raise ValueError("Invalid numeric value") from exc
    if value<0:raise ValueError("Quantity cannot be negative")
    return value
def validate_job(db:Session,job:ImportJob,mapping:dict[str,str],include_rows=True)->ValidationSummary:
    if job.status not in (ImportStatus.PREVIEWED,ImportStatus.VALIDATED):raise HTTPException(409,"Import job cannot be validated in its current status")
    try:validate_mapping(mapping)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    db.execute(delete(ImportError).where(ImportError.import_job_id==job.id));valid=warning=errors=0;output=[]
    for row in db.scalars(select(ImportRow).where(ImportRow.import_job_id==job.id).order_by(ImportRow.row_number)):
        mapped={target:row.raw_data.get(source) for source,target in mapping.items() if target};issues=[]
        def issue(severity:ImportSeverity,column:str,code:str,message:str):issues.append((severity,column,code,message,mapped.get(column)))
        if not str(mapped.get("container_number") or "").strip():issue(ImportSeverity.ERROR,"container_number","REQUIRED","Container Number is required")
        wh_value=str(mapped.get("warehouse") or "").strip();warehouse=db.scalar(select(Warehouse).where(or_(func.lower(Warehouse.warehouse_code)==wh_value.lower(),func.lower(Warehouse.warehouse_name)==wh_value.lower()))) if wh_value else None
        if not warehouse:issue(ImportSeverity.ERROR,"warehouse","UNKNOWN_WAREHOUSE","Warehouse does not exist")
        customer=None;cust_value=str(mapped.get("customer") or "").strip()
        if cust_value:
            customer=db.scalar(select(Customer).where(or_(func.lower(Customer.customer_code)==cust_value.lower(),func.lower(Customer.customer_name)==cust_value.lower())))
            if not customer:issue(ImportSeverity.WARNING,"customer","UNKNOWN_CUSTOMER","Customer does not exist; value will be left empty")
        location=None;loc_value=str(mapped.get("location") or "").strip()
        if loc_value and warehouse:
            location=db.scalar(select(WarehouseLocation).where(WarehouseLocation.warehouse_id==warehouse.id,func.lower(WarehouseLocation.location_code)==loc_value.lower()))
            if not location:issue(ImportSeverity.WARNING,"location","UNKNOWN_LOCATION","Location does not exist in selected warehouse; value will be left empty")
        parsed={}
        for field in ("unload_date","received_date"):
            try:parsed[field]=_date(mapped.get(field))
            except ValueError:issue(ImportSeverity.ERROR,field,"INVALID_DATE","Invalid date format")
        for field in ("pallet_qty","carton_qty","weight_lbs","cbm"):
            try:parsed[field]=_decimal(mapped.get(field))
            except ValueError as exc:issue(ImportSeverity.ERROR,field,"INVALID_NUMERIC",str(exc))
        stable_date=parsed.get("received_date") or parsed.get("unload_date")
        if warehouse and stable_date:
            duplicate=db.scalar(select(InboundRecord.id).where(InboundRecord.container_number==str(mapped.get("container_number") or "").strip(),InboundRecord.fc_code==(str(mapped.get("fc_code")).strip() if mapped.get("fc_code") else None),InboundRecord.warehouse_id==warehouse.id,func.coalesce(InboundRecord.received_date,InboundRecord.unload_date)==stable_date,InboundRecord.location_id==(location.id if location else None)))
            if duplicate:issue(ImportSeverity.WARNING,"container_number","DUPLICATE",f"Matches inbound record {duplicate}")
        elif warehouse:issue(ImportSeverity.WARNING,"received_date","UNSTABLE_DUPLICATE_KEY","No received/unload date; duplicate key is incomplete")
        for severity,column,code,message,raw in issues:db.add(ImportError(import_job_id=job.id,row_number=row.row_number,column_name=column,raw_value=None if raw is None else str(raw),severity=severity,error_code=code,error_message=message))
        has_error=any(x[0]==ImportSeverity.ERROR for x in issues);has_warning=any(x[0]==ImportSeverity.WARNING for x in issues);row.validation_status=RowValidationStatus.ERROR if has_error else RowValidationStatus.WARNING if has_warning else RowValidationStatus.VALID;row.mapped_data={**mapped,**{k:v.isoformat() if isinstance(v,date) else str(v) if isinstance(v,Decimal) else v for k,v in parsed.items()},"warehouse_id":warehouse.id if warehouse else None,"customer_id":customer.id if customer else None,"location_id":location.id if location else None};errors+=has_error;warning+=has_warning and not has_error;valid+=not has_error
        if include_rows and len(output)<100:output.append({"row_number":row.row_number,"data":row.mapped_data,"status":row.validation_status.value,"issues":[{"severity":x[0].value,"column":x[1],"code":x[2],"message":x[3]} for x in issues]})
    job.mapping=mapping;job.valid_rows=valid;job.warning_rows=warning;job.error_rows=errors;job.status=ImportStatus.VALIDATED;db.commit();return ValidationSummary(job_id=job.id,total_rows=job.total_rows,valid_rows=valid,warning_rows=warning,error_rows=errors,rows=output)
def confirm_job(db:Session,job:ImportJob,mapping:dict[str,str],strategy:str,user_id:int)->ImportSummary:
    if job.status not in (ImportStatus.PREVIEWED,ImportStatus.VALIDATED):raise HTTPException(409,"Import job cannot be confirmed in its current status")
    summary=validate_job(db,job,mapping,False);job.status=ImportStatus.IMPORTING;db.flush();imported=skipped=0
    try:
        for row in db.scalars(select(ImportRow).where(ImportRow.import_job_id==job.id).order_by(ImportRow.row_number)):
            if row.validation_status==RowValidationStatus.ERROR:skipped+=1;continue
            d=row.mapped_data or {};received=_date(d.get("received_date"));unload=_date(d.get("unload_date"));existing=None
            if received or unload:existing=db.scalar(select(InboundRecord).where(InboundRecord.container_number==str(d.get("container_number") or "").strip(),InboundRecord.fc_code==(str(d.get("fc_code")).strip() if d.get("fc_code") else None),InboundRecord.warehouse_id==d["warehouse_id"],func.coalesce(InboundRecord.received_date,InboundRecord.unload_date)==(received or unload),InboundRecord.location_id==d.get("location_id")))
            payload=InboundCreate(container_number=str(d["container_number"]).strip(),customer_id=d.get("customer_id"),warehouse_id=d["warehouse_id"],unload_date=unload,received_date=received,fc_code=str(d.get("fc_code") or "").strip() or None,marking=str(d.get("marking") or "").strip() or None,pallet_qty=_decimal(d.get("pallet_qty")) or 0,carton_qty=_decimal(d.get("carton_qty")) or 0,weight_lbs=_decimal(d.get("weight_lbs")),cbm=_decimal(d.get("cbm")),location_id=d.get("location_id"),status=InboundStatus.PENDING,remark=str(d.get("remark") or "").strip() or None)
            if existing and strategy=="SKIP":row.validation_status=RowValidationStatus.SKIPPED;skipped+=1;continue
            if existing:
                for k,v in payload.model_dump().items():setattr(existing,k,v)
                existing.import_job_id=job.id
                entity=existing
            else:entity=create_inbound(db,payload,user_id,job.id,False)
            db.flush();row.created_entity_type="INBOUND";row.created_entity_id=entity.id;row.validation_status=RowValidationStatus.IMPORTED;imported+=1
        job.imported_rows=imported;job.status=ImportStatus.COMPLETED;job.completed_at=datetime.now(UTC);db.add(AuditLog(user_id=user_id,action="IMPORT",entity_type="INBOUND",entity_id=job.id,after_data={"imported_rows":imported,"skipped_rows":skipped}));db.commit()
    except Exception:db.rollback();job=db.get(ImportJob,job.id);job.status=ImportStatus.FAILED;db.commit();raise
    return ImportSummary(job_id=job.id,total_rows=summary.total_rows,imported_rows=imported,skipped_rows=skipped,warning_rows=summary.warning_rows,error_rows=summary.error_rows)
