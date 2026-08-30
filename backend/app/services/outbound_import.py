from datetime import UTC,datetime
from decimal import Decimal,InvalidOperation
from fastapi import HTTPException
from sqlalchemy import delete,func,or_,select
from sqlalchemy.orm import Session
from app.imports.mapping import validate_outbound_mapping
from app.models import AuditLog,Carrier,Customer,FBAInventoryAllocation,FBAShipment,ImportError,ImportJob,ImportRow,InventoryLot,OutboundOrder,Warehouse
from app.models.import_job import ImportSeverity,ImportStatus,RowValidationStatus
from app.schemas.imports import ImportSummary,ValidationSummary
from app.schemas.outbound import AllocateRequest,OBCreate
from app.services.outbound import allocate,create_ob
from app.utils.business_time import to_business_datetime
def num(v):
 if v in(None,''):return Decimal('0')
 try:d=Decimal(str(v).replace(',','').strip())
 except InvalidOperation as e:raise ValueError('Invalid numeric value') from e
 if d<0:raise ValueError('Quantity cannot be negative')
 return d
def parsed_datetime(v):
 if v in(None,''):return None
 if isinstance(v,datetime):return to_business_datetime(v)
 try:return to_business_datetime(datetime.fromisoformat(str(v).strip()))
 except ValueError:
  for fmt in ('%m/%d/%Y','%Y/%m/%d','%m/%d/%y'):
   try:return to_business_datetime(datetime.strptime(str(v).strip(),fmt))
   except ValueError:pass
 raise ValueError('Invalid outbound date')
def _map(row,mapping):return {target:row.raw_data.get(source) for source,target in mapping.items() if target}
def validate_outbound_job(db:Session,job:ImportJob,mapping:dict[str,str],include_rows=True):
 if job.status not in (ImportStatus.PREVIEWED,ImportStatus.VALIDATED):raise HTTPException(409,'Import job cannot be validated in its current status')
 try:validate_outbound_mapping(mapping)
 except ValueError as e:raise HTTPException(422,str(e)) from e
 db.execute(delete(ImportError).where(ImportError.import_job_id==job.id));valid=warn=err=0;preview=[];cum={}
 rows=db.scalars(select(ImportRow).where(ImportRow.import_job_id==job.id).order_by(ImportRow.row_number)).all()
 for row in rows:
  d=_map(row,mapping);issues=[]
  def issue(sev,col,code,msg):issues.append((sev,col,code,msg,d.get(col)))
  whv=str(d.get('warehouse') or '').strip();wh=db.scalar(select(Warehouse).where(or_(func.lower(Warehouse.warehouse_code)==whv.lower(),func.lower(Warehouse.warehouse_name)==whv.lower()))) if whv else None
  if not wh:issue(ImportSeverity.ERROR,'warehouse','UNKNOWN_WAREHOUSE','Warehouse does not exist')
  container=str(d.get('container_number') or '').strip();lot=None
  if not container:issue(ImportSeverity.ERROR,'container_number','REQUIRED','Container Number is required')
  elif wh:
   lv=str(d.get('lot_no') or '').strip();q=select(InventoryLot).where(InventoryLot.warehouse_id==wh.id)
   q=q.where(InventoryLot.lot_no==lv) if lv else q.where(InventoryLot.container_number==container)
   lots=list(db.scalars(q).all())
   if not lots:issue(ImportSeverity.ERROR,'container_number','UNKNOWN_INVENTORY','Inventory lot does not exist')
   elif len(lots)>1:issue(ImportSeverity.ERROR,'container_number','ERROR_AMBIGUOUS_INVENTORY','Multiple inventory lots match')
   else:lot=lots[0]
  vals={}
  for f in ('pallet_qty','carton_qty','weight_lbs','cbm'):
   try:vals[f]=num(d.get(f))
   except ValueError as e:issue(ImportSeverity.ERROR,f,'INVALID_NUMERIC',str(e));vals[f]=Decimal('0')
  try:outbound_at=parsed_datetime(d.get('schedule_pickup_at'))
  except ValueError as e:issue(ImportSeverity.ERROR,'schedule_pickup_at','INVALID_DATE',str(e));outbound_at=None
  typ=str(d.get('ob_type') or 'STANDARD').upper();fba_no=str(d.get('fba_no') or '').strip();fa=None
  if typ=='FBA':
   fba=db.scalar(select(FBAShipment).where(FBAShipment.fba_no==fba_no)) if fba_no else None
   if not fba:issue(ImportSeverity.ERROR,'fba_no','UNKNOWN_FBA','FBA shipment does not exist')
   elif lot:
    fa=db.scalar(select(FBAInventoryAllocation).where(FBAInventoryAllocation.fba_shipment_id==fba.id,FBAInventoryAllocation.inventory_lot_id==lot.id))
    if not fa:issue(ImportSeverity.ERROR,'container_number','UNKNOWN_FBA_ALLOCATION','FBA allocation does not exist for inventory lot')
  if lot:
   key=(lot.id,fa.id if fa else None);used=cum.setdefault(key,[Decimal('0')]*4)
   limits=(lot.available_pallet_qty,lot.available_carton_qty,lot.available_weight_lbs,lot.available_cbm) if not fa else (fa.allocated_pallet_qty,fa.allocated_carton_qty,fa.allocated_weight_lbs,fa.allocated_cbm)
   for i,f in enumerate(('pallet_qty','carton_qty','weight_lbs','cbm')):used[i]+=vals[f]
   if any(x>y for x,y in zip(used,limits)):issue(ImportSeverity.ERROR,'pallet_qty','OVER_ALLOCATION','Import exceeds available source quantity')
  for field,model,col,codecol,namecol in [('customer',Customer,'customer','customer_code','customer_name'),('carrier',Carrier,'carrier','carrier_code','carrier_name')]:
   value=str(d.get(field) or '').strip()
   if value and db.scalar(select(model).where(or_(func.lower(getattr(model,codecol))==value.lower(),func.lower(getattr(model,namecol))==value.lower()))) is None:issue(ImportSeverity.WARNING,col,'UNKNOWN_'+field.upper(),f'{field.title()} not found')
  for s,c,code,msg,raw in issues:db.add(ImportError(import_job_id=job.id,row_number=row.row_number,column_name=c,raw_value=None if raw is None else str(raw),severity=s,error_code=code,error_message=msg))
  has=any(x[0]==ImportSeverity.ERROR for x in issues);hasw=any(x[0]==ImportSeverity.WARNING for x in issues);row.validation_status=RowValidationStatus.ERROR if has else RowValidationStatus.WARNING if hasw else RowValidationStatus.VALID;row.mapped_data={**d,**{k:str(v) for k,v in vals.items()},'schedule_pickup_at':outbound_at.isoformat() if outbound_at else None,'warehouse_id':wh.id if wh else None,'inventory_lot_id':lot.id if lot else None,'fba_allocation_id':fa.id if fa else None,'ob_type':typ};err+=has;warn+=hasw and not has;valid+=not has
  if include_rows and len(preview)<100:preview.append({'row_number':row.row_number,'data':row.mapped_data,'status':row.validation_status.value,'issues':[{'severity':x[0].value,'column':x[1],'code':x[2],'message':x[3]} for x in issues]})
 job.mapping=mapping;job.valid_rows=valid;job.warning_rows=warn;job.error_rows=err;job.status=ImportStatus.VALIDATED;db.commit();return ValidationSummary(job_id=job.id,total_rows=job.total_rows,valid_rows=valid,warning_rows=warn,error_rows=err,rows=preview)
def confirm_outbound_job(db:Session,job:ImportJob,mapping,user_id:int,duplicate_strategy='SKIP'):
 summary=validate_outbound_job(db,job,mapping,False);job.status=ImportStatus.IMPORTING;db.flush();groups={};imported=skipped=0
 try:
  for row in db.scalars(select(ImportRow).where(ImportRow.import_job_id==job.id).order_by(ImportRow.row_number)):
   if row.validation_status==RowValidationStatus.ERROR:skipped+=1;continue
   d=row.mapped_data;group=str(d.get('ob_no') or '').strip() or f'ROW-{row.row_number}';o=groups.get(group)
   if not o:
    supplied=str(d.get('ob_no') or '').strip();o=db.scalar(select(OutboundOrder).where(OutboundOrder.ob_no==supplied)) if supplied else None
    if o and (duplicate_strategy=='UPDATE' and o.status!=0):raise HTTPException(409,'Only New outbound orders may be updated')
    if not o:o=create_ob(db,OBCreate(warehouse_id=d['warehouse_id'],customer_id=d.get('customer_id'),carrier_id=d.get('carrier_id'),fba_shipment_id=None,ob_type=d.get('ob_type','STANDARD'),loading_team=d.get('loading_team'),truck_type=d.get('truck_type'),delivery_type=d.get('delivery_type'),pickup_location=d.get('pickup_location'),schedule_pickup_at=parsed_datetime(d.get('schedule_pickup_at')),fc_code=d.get('fc_code'),del_code=d.get('del_code'),agent_code=d.get('agent_code'),reference_no=d.get('reference_no'),remark=d.get('remark')),user_id,supplied or None,False)
    groups[group]=o
   allocate(db,o.id,AllocateRequest(inventory_lot_id=d['inventory_lot_id'],fba_allocation_id=d.get('fba_allocation_id'),pallet_qty=num(d.get('pallet_qty')),carton_qty=num(d.get('carton_qty')),weight_lbs=num(d.get('weight_lbs')),cbm=num(d.get('cbm'))),user_id,False);row.created_entity_type='OUTBOUND';row.created_entity_id=o.id;row.validation_status=RowValidationStatus.IMPORTED;imported+=1
  job.imported_rows=imported;job.status=ImportStatus.COMPLETED;job.completed_at=datetime.now(UTC);db.add(AuditLog(user_id=user_id,action='IMPORT_OUTBOUND',entity_type='IMPORT_JOB',entity_id=job.id,after_data={'rows':imported,'outbounds':len(groups)}));db.commit()
 except Exception:db.rollback();failed=db.get(ImportJob,job.id);failed.status=ImportStatus.FAILED;db.commit();raise
 return ImportSummary(job_id=job.id,total_rows=summary.total_rows,imported_rows=imported,skipped_rows=skipped,warning_rows=summary.warning_rows,error_rows=summary.error_rows)
