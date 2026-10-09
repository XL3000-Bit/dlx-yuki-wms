from datetime import UTC,datetime
from decimal import Decimal,InvalidOperation
from typing import Any
from fastapi import HTTPException
from sqlalchemy import delete,func,or_,select
from sqlalchemy.orm import Session
from app.imports.mapping import validate_fba_mapping
from app.models import AmazonFCAddress,AuditLog,Carrier,Customer,FBAInventoryAllocation,FBAShipment,ImportError,ImportJob,ImportRow,InventoryLot,Warehouse
from app.models.import_job import ImportSeverity,ImportStatus,RowValidationStatus
from app.schemas.fba import AllocateRequest,FBACreate
from app.schemas.imports import ImportSummary,ValidationSummary
from app.services.fba import allocate,create_fba

def dec(v:Any)->Decimal:
    if v in(None,""):return Decimal("0")
    try:d=Decimal(str(v).replace(",","").strip())
    except InvalidOperation as exc:raise ValueError("Invalid numeric value")from exc
    if d<0:raise ValueError("Quantity cannot be negative")
    return d
def dt(v:Any)->datetime|None:
    if v in(None,""):return None
    if isinstance(v,datetime):return v
    value=str(v).strip()
    for fmt in("%Y-%m-%d %H:%M","%Y-%m-%d","%m/%d/%Y %H:%M","%m/%d/%Y"):
        try:return datetime.strptime(value,fmt)
        except ValueError:pass
    raise ValueError("Invalid datetime")
def validate_fba_job(db:Session,job:ImportJob,mapping:dict[str,str],include_rows=True)->ValidationSummary:
    if job.status not in(ImportStatus.PREVIEWED,ImportStatus.VALIDATED):raise HTTPException(409,"Import job cannot be validated in its current status")
    try:validate_fba_mapping(mapping)
    except ValueError as exc:raise HTTPException(422,str(exc))from exc
    db.execute(delete(ImportError).where(ImportError.import_job_id==job.id));valid=warnings=errors=0;output=[];requested_by_lot:dict[int,list[Decimal]]={};groups={};validated=[]
    for row in db.scalars(select(ImportRow).where(ImportRow.import_job_id==job.id).order_by(ImportRow.row_number)):
        mapped={target:row.raw_data.get(source)for source,target in mapping.items()if target};issues=[]
        def issue(severity,column,code,message):issues.append((severity,column,code,message,mapped.get(column)))
        warehouse_value=str(mapped.get("warehouse")or"").strip();warehouse=db.scalar(select(Warehouse).where(or_(func.lower(Warehouse.warehouse_code)==warehouse_value.lower(),func.lower(Warehouse.warehouse_name)==warehouse_value.lower())))if warehouse_value else None
        if not warehouse:issue(ImportSeverity.ERROR,"warehouse","UNKNOWN_WAREHOUSE","Warehouse does not exist")
        fc=str(mapped.get("amazon_fc_code")or"").strip().upper()
        if not fc:issue(ImportSeverity.ERROR,"amazon_fc_code","REQUIRED","Amazon FC is required")
        elif db.scalar(select(AmazonFCAddress.id).where(AmazonFCAddress.fc_code==fc))is None:issue(ImportSeverity.WARNING,"amazon_fc_code","UNKNOWN_FC_ADDRESS","Amazon FC address is not configured")
        container=str(mapped.get("container_number")or"").strip();lot=None
        if not container:issue(ImportSeverity.ERROR,"container_number","REQUIRED","Container Number is required")
        elif warehouse:
            lots=list(db.scalars(select(InventoryLot).where(InventoryLot.warehouse_id==warehouse.id,InventoryLot.container_number==container)).all())
            if not lots:issue(ImportSeverity.ERROR,"container_number","UNKNOWN_INVENTORY","No inventory lot matches container and warehouse")
            elif len(lots)>1:issue(ImportSeverity.ERROR,"container_number","AMBIGUOUS_INVENTORY","Multiple inventory lots match container")
            else:lot=lots[0]
        parsed={}
        for field in("pallet_qty","carton_qty","weight_lbs","cbm"):
            try:parsed[field]=dec(mapped.get(field))
            except ValueError as exc:issue(ImportSeverity.ERROR,field,"INVALID_NUMERIC",str(exc));parsed[field]=Decimal("0")
        for field in("scheduled_pickup_at","appointment_time"):
            try:parsed[field]=dt(mapped.get(field))
            except ValueError:issue(ImportSeverity.ERROR,field,"INVALID_DATE","Invalid date/time");parsed[field]=None
        if lot:
            cumulative=requested_by_lot.setdefault(lot.id,[Decimal("0")]*4)
            for i,field in enumerate(("pallet_qty","carton_qty","weight_lbs","cbm")):cumulative[i]+=parsed[field]
            available=(lot.available_pallet_qty,lot.available_carton_qty,lot.available_weight_lbs,lot.available_cbm)
            if any(x>y for x,y in zip(cumulative,available)):issue(ImportSeverity.ERROR,"pallet_qty","OVER_ALLOCATION","Import allocation exceeds currently available inventory")
            if lot.fc_code and fc and lot.fc_code.upper()!=fc:issue(ImportSeverity.ERROR,"amazon_fc_code","FC_MISMATCH","Inventory FC differs from FBA FC")
            supplied_fba=str(mapped.get("fba_no")or"").strip()
            existing_fba=db.scalar(select(FBAShipment).where(FBAShipment.fba_no==supplied_fba))if supplied_fba else None
            if existing_fba and db.scalar(select(FBAInventoryAllocation.id).where(FBAInventoryAllocation.fba_shipment_id==existing_fba.id,FBAInventoryAllocation.inventory_lot_id==lot.id)) is not None:issue(ImportSeverity.ERROR,"container_number","DUPLICATE_ALLOCATION","Inventory lot is already allocated to this FBA")
        customer_value=str(mapped.get("customer")or"").strip();customer=db.scalar(select(Customer).where(or_(func.lower(Customer.customer_code)==customer_value.lower(),func.lower(Customer.customer_name)==customer_value.lower())))if customer_value else None
        if customer_value and not customer:issue(ImportSeverity.ERROR,"customer","UNKNOWN_CUSTOMER","Customer not found")
        if not customer_value and lot and lot.customer_id:
            # The uniquely resolved source lot is evidence of ownership.
            customer=db.get(Customer,lot.customer_id)
        if lot and (customer is None or customer.id!=lot.customer_id):issue(ImportSeverity.ERROR,"customer","CUSTOMER_OWNERSHIP_MISMATCH","Customer must match the source inventory lot")
        if lot and existing_fba and (existing_fba.warehouse_id,existing_fba.customer_id,existing_fba.amazon_fc_code)!=(warehouse.id,customer.id if customer else None,fc):issue(ImportSeverity.ERROR,"fba_no","FBA_OWNERSHIP_MISMATCH","Existing FBA warehouse, customer or destination differs")
        carrier_value=str(mapped.get("carrier")or"").strip();carrier=db.scalar(select(Carrier).where(or_(func.lower(Carrier.carrier_code)==carrier_value.lower(),func.lower(Carrier.carrier_name)==carrier_value.lower())))if carrier_value else None
        if carrier_value and not carrier:issue(ImportSeverity.WARNING,"carrier","UNKNOWN_CARRIER","Carrier not found")
        group=str(mapped.get("fba_no")or mapped.get("shipment_id")or f"ROW-{row.row_number}").strip()
        groups.setdefault(group,[]).append((row,issues,(warehouse.id if warehouse else None,customer.id if customer else None,fc)))
        validated.append((row,issues))
        has_error=any(x[0]==ImportSeverity.ERROR for x in issues);has_warning=any(x[0]==ImportSeverity.WARNING for x in issues);row.validation_status=RowValidationStatus.ERROR if has_error else RowValidationStatus.WARNING if has_warning else RowValidationStatus.VALID;row.mapped_data={**mapped,**{k:v.isoformat()if isinstance(v,datetime)else str(v)if isinstance(v,Decimal)else v for k,v in parsed.items()},"warehouse_id":warehouse.id if warehouse else None,"customer_id":customer.id if customer else None,"carrier_id":carrier.id if carrier else None,"inventory_lot_id":lot.id if lot else None,"amazon_fc_code":fc};errors+=has_error;warnings+=has_warning and not has_error;valid+=not has_error
    valid=warnings=errors=0
    for entries in groups.values():
        if len({signature for _,_,signature in entries})>1:
            for row,issues,_ in entries:issues.append((ImportSeverity.ERROR,"fba_no","MIXED_FBA_GROUP","One FBA group must use one warehouse, customer and destination",row.mapped_data.get("fba_no")))
    for row,issues in validated:
        for severity,column,code,message,raw in issues:db.add(ImportError(import_job_id=job.id,row_number=row.row_number,column_name=column,raw_value=None if raw is None else str(raw),severity=severity,error_code=code,error_message=message))
        has_error=any(x[0]==ImportSeverity.ERROR for x in issues);has_warning=any(x[0]==ImportSeverity.WARNING for x in issues)
        row.validation_status=RowValidationStatus.ERROR if has_error else RowValidationStatus.WARNING if has_warning else RowValidationStatus.VALID
        errors+=has_error;warnings+=has_warning and not has_error;valid+=not has_error
        if include_rows and len(output)<100:output.append({"row_number":row.row_number,"data":row.mapped_data,"status":row.validation_status.value,"issues":[{"severity":x[0].value,"column":x[1],"code":x[2],"message":x[3]}for x in issues]})
    job.mapping=mapping;job.valid_rows=valid;job.warning_rows=warnings;job.error_rows=errors;job.status=ImportStatus.VALIDATED;db.commit();return ValidationSummary(job_id=job.id,total_rows=job.total_rows,valid_rows=valid,warning_rows=warnings,error_rows=errors,rows=output)
def confirm_fba_job(db:Session,job:ImportJob,mapping:dict[str,str],user_id:int)->ImportSummary:
    if job.status not in(ImportStatus.PREVIEWED,ImportStatus.VALIDATED):raise HTTPException(409,"Import job cannot be confirmed in its current status")
    summary=validate_fba_job(db,job,mapping,False);job.status=ImportStatus.IMPORTING;db.flush();shipments:dict[str,FBAShipment]={};imported=skipped=0
    try:
        for row in db.scalars(select(ImportRow).where(ImportRow.import_job_id==job.id).order_by(ImportRow.row_number)):
            if row.validation_status==RowValidationStatus.ERROR:skipped+=1;continue
            d=row.mapped_data or{};group=str(d.get("fba_no")or d.get("shipment_id")or f"ROW-{row.row_number}").strip();shipment=shipments.get(group)
            if shipment is None:
                supplied=str(d.get("fba_no")or"").strip()or None;shipment=db.scalar(select(FBAShipment).where(FBAShipment.fba_no==supplied))if supplied else None
                if shipment is None:shipment=create_fba(db,FBACreate(customer_id=d.get("customer_id"),warehouse_id=d["warehouse_id"],amazon_fc_code=d["amazon_fc_code"],carrier_id=d.get("carrier_id"),scheduled_pickup_at=dt(d.get("scheduled_pickup_at")),appointment_time=dt(d.get("appointment_time")),reference_no=str(d.get("reference_no")or"")or None,shipment_id=str(d.get("shipment_id")or"")or None,st_number=str(d.get("st_number")or"")or None,remark=str(d.get("remark")or"")or None),user_id,supplied,False)
                shipments[group]=shipment
            allocation=allocate(db,shipment.id,AllocateRequest(inventory_lot_id=d["inventory_lot_id"],pallet_qty=dec(d.get("pallet_qty")),carton_qty=dec(d.get("carton_qty")),weight_lbs=dec(d.get("weight_lbs")),cbm=dec(d.get("cbm")),confirm_fc_mismatch=False),user_id,False);db.flush();row.created_entity_type="FBA";row.created_entity_id=shipment.id;row.validation_status=RowValidationStatus.IMPORTED;imported+=1
        job.imported_rows=imported;job.status=ImportStatus.COMPLETED;job.completed_at=datetime.now(UTC);db.add(AuditLog(user_id=user_id,action="IMPORT_FBA",entity_type="IMPORT_JOB",entity_id=job.id,after_data={"shipments":len(shipments),"rows":imported}));db.commit()
    except Exception:db.rollback();failed=db.get(ImportJob,job.id);failed.status=ImportStatus.FAILED;db.commit();raise
    return ImportSummary(job_id=job.id,total_rows=summary.total_rows,imported_rows=imported,skipped_rows=skipped,warning_rows=summary.warning_rows,error_rows=summary.error_rows)
