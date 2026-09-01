import csv,hashlib,io
from datetime import datetime,timezone
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.models import ContainerTracking,TrackingStatus,Warehouse,AuditLog,User
from app.services.access_policy import assert_warehouse_access
HEADERS={
 'MBL#':'mbl_number','HBL#':'hbl_number','Filling#':'filing_number','Container':'container_number',
 'Container Attributes':'container_attributes','Container Remark':'container_remark','Customer Ref#':'customer_reference',
 'POD ETA':'pod_eta','IR ETA':'ir_eta','POD':'pod','DEL(IR) Location':'delivery_location','F.DEST':'final_destination',
 'DEL Warehouse':'delivery_warehouse_raw','Schedule Delivery Date':'scheduled_delivery_at',
 'Actual Delivery Date':'actual_delivery_at','WA Received At':'wa_received_at','WA Empty At':'wa_empty_at',
 'WA Complete At':'wa_complete_at',
 'mbl_number':'mbl_number','hbl_number':'hbl_number','container_number':'container_number',
 'container_attributes':'container_attributes','container_remark':'container_remark',
 'customer_reference':'customer_reference','pod_eta':'pod_eta','ir_eta':'ir_eta',
 'actual_delivery_at':'actual_delivery_at','wa_received_at':'wa_received_at','wa_complete_at':'wa_complete_at',
 '柜号':'container_number','客户':'customer_reference','ETA':'pod_eta',
}
def parse_dt(v):
 if not v:return None
 for f in ('%Y-%m-%d %H:%M:%S','%Y-%m-%d','%m/%d/%Y %H:%M','%m/%d/%Y'):
  try:return datetime.strptime(str(v).strip(),f).replace(tzinfo=timezone.utc)
  except ValueError:pass
 raise ValueError('Invalid date')
def normalize(raw):
 folded={str(k).strip():v for k,v in raw.items()}
 d={}
 for src,dst in HEADERS.items():
  value=((folded.get(src) or '').strip() or None)
  if value and not d.get(dst):d[dst]=value
  elif dst not in d:d[dst]=value
 d['container_number']=(d.get('container_number') or '').upper()
 for k in ('pod_eta','ir_eta','scheduled_delivery_at','actual_delivery_at','wa_received_at','wa_empty_at','wa_complete_at'):d[k]=parse_dt(d[k])
 return d
def fingerprint(d):return hashlib.sha256('|'.join(str(d.get(k) or '') for k in ('container_number','mbl_number','pod_eta')).encode()).hexdigest()
def status(d):
 for k,s in [('wa_complete_at',TrackingStatus.COMPLETED),('wa_empty_at',TrackingStatus.EMPTY),('wa_received_at',TrackingStatus.WAREHOUSE_RECEIVED),('actual_delivery_at',TrackingStatus.DELIVERED),('scheduled_delivery_at',TrackingStatus.DELIVERY_SCHEDULED),('pod_eta',TrackingStatus.IN_TRANSIT)]:
  if d.get(k):return s
 return TrackingStatus.PLANNED
def anomalies(d):
 pairs=[('actual_delivery_at','scheduled_delivery_at','ACTUAL_DELIVERY_BEFORE_SCHEDULE'),('wa_received_at','actual_delivery_at','RECEIVED_BEFORE_ACTUAL_DELIVERY'),('wa_empty_at','wa_received_at','EMPTY_BEFORE_RECEIVED'),('wa_complete_at','wa_empty_at','COMPLETE_BEFORE_EMPTY')]
 return [c for l,e,c in pairs if d.get(l) and d.get(e) and d[l]<d[e]]
def import_csv(db:Session,content:bytes,file_name:str,user:User,limit=None):
 rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))));out={'rows':len(rows),'created':0,'updated':0,'warnings':0,'errors':0,'anomalies':0,'warehouse_unknown':0,'inventory_created':0}
 for idx,raw in enumerate(rows[:limit] if limit else rows,2):
  try:
   d=normalize(raw)
   if not d['container_number']:out['errors']+=1;continue
   d.update(source_fingerprint=fingerprint(d),source_file_name=file_name,source_row_number=idx,source_type='SHIPMENT_EXPORT',tracking_status=status(d))
   wh=db.scalar(select(Warehouse).where(func.upper(Warehouse.warehouse_code)==(d.get('delivery_warehouse_raw') or '').upper())) if d.get('delivery_warehouse_raw') else None;d['warehouse_id']=wh.id if wh else None
   assert_warehouse_access(user,d['warehouse_id'])
   if d.get('delivery_warehouse_raw') and not wh:out['warehouse_unknown']+=1;out['warnings']+=1
   obj=db.scalar(select(ContainerTracking).where(ContainerTracking.source_fingerprint==d['source_fingerprint'])) or db.scalar(select(ContainerTracking).where(ContainerTracking.container_number==d['container_number'],ContainerTracking.mbl_number==d.get('mbl_number'),ContainerTracking.pod_eta==d.get('pod_eta')))
   if obj:
    for k,v in d.items():
     if v is not None:setattr(obj,k,v)
    out['updated']+=1
   else:db.add(ContainerTracking(**d));out['created']+=1
   aa=anomalies(d);out['anomalies']+=len(aa);out['warnings']+=bool(aa)
  except Exception:out['errors']+=1
 db.commit();return out
