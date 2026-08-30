from datetime import UTC,date,datetime
from decimal import Decimal
from io import BytesIO
from sqlalchemy import func,select
from sqlalchemy.orm import Session,joinedload
from fastapi import HTTPException
from fastapi.responses import Response
from openpyxl import Workbook
from app.models import AuditLog,BOL,BOLItem,FBAShipment,InventoryLot,OutboundInventoryAllocation,OutboundOrder,PickingList,PickingListItem
from app.models.bol import BOLStatus
from app.models.picking import PickingStatus
from app.schemas.picking_bol import BOLRead,PickComplete,PickingRead
from app.services.outbound import get_ob
from app.utils.business_time import get_business_today,to_business_date
PICK_NAMES={0:'New',1:'Printed',2:'In Progress',3:'Completed',4:'Canceled',5:'Exception'};BOL_NAMES={0:'Draft',1:'Generated',2:'Printed',3:'Completed',4:'Canceled'}
def number(db,model,prefix):
 p=f'{prefix}{get_business_today():%y%m%d}';last=db.scalar(select(func.max(model.picking_no if model is PickingList else model.bol_no)).where((model.picking_no if model is PickingList else model.bol_no).like(p+'%')));return f'{p}{(int(last[-4:])+1 if last else 1):04d}'
def picking_read(p):return PickingRead.model_validate({**p.__dict__,'status_name':PICK_NAMES[p.status],'planned_pallet_qty':sum((i.planned_pallet_qty for i in p.items),Decimal(0)),'planned_carton_qty':sum((i.planned_carton_qty for i in p.items),Decimal(0)),'picked_pallet_qty':sum((i.picked_pallet_qty for i in p.items),Decimal(0)),'picked_carton_qty':sum((i.picked_carton_qty for i in p.items),Decimal(0))})
def generate_picking(db:Session,ob_id,user_id):
 o=get_ob(db,ob_id);allocs=list(db.scalars(select(OutboundInventoryAllocation).options(joinedload(OutboundInventoryAllocation.inventory_lot)).where(OutboundInventoryAllocation.outbound_order_id==ob_id)).all())
 if not allocs:raise HTTPException(409,'Outbound requires allocations')
 planned={i.outbound_allocation_id for i in db.scalars(select(PickingListItem).join(PickingList).where(PickingList.outbound_order_id==ob_id,PickingList.status!=PickingStatus.CANCELED)).all()};p=PickingList(picking_no=number(db,PickingList,'PK'),outbound_order_id=ob_id,status=0,created_by=user_id);db.add(p);db.flush()
 for seq,a in enumerate(sorted(allocs,key=lambda x:(x.inventory_lot.location_id or 0,x.inventory_lot.inbound_date or date.max)),1):
  existing=db.scalars(select(PickingListItem).where(PickingListItem.outbound_allocation_id==a.id)).all();usedp=sum((i.planned_pallet_qty for i in existing),Decimal(0));usedc=sum((i.planned_carton_qty for i in existing),Decimal(0));rp=a.allocated_pallet_qty-a.completed_pallet_qty-usedp;rc=a.allocated_carton_qty-a.completed_carton_qty-usedc
  if rp<=0 and rc<=0:continue
  l=a.inventory_lot;p.items.append(PickingListItem(outbound_allocation_id=a.id,inventory_lot_id=l.id,location_id=l.location_id,lot_no=l.lot_no,container_number=l.container_number,fc_code=l.fc_code,marking=l.marking,planned_pallet_qty=rp,planned_carton_qty=rc,planned_weight_lbs=a.allocated_weight_lbs-a.completed_weight_lbs,planned_cbm=a.allocated_cbm-a.completed_cbm,sequence_no=seq))
 db.add(AuditLog(user_id=user_id,action='CREATE_PICKING_LIST',entity_type='PICKING',entity_id=p.id));db.commit();return p
def complete_picking(db:Session,pid:int,user_id:int,payload:PickComplete|None=None):
 p=db.get(PickingList,pid)
 if not p:raise HTTPException(404,'Picking list not found')
 if p.status in (3,4):raise HTTPException(409,'Picking list is closed')
 for i in p.items:i.picked_pallet_qty=payload.picked_pallet_qty if payload and payload.picked_pallet_qty is not None else i.planned_pallet_qty;i.picked_carton_qty=payload.picked_carton_qty if payload and payload.picked_carton_qty is not None else i.planned_carton_qty
 p.status=3;p.completed_at=datetime.now(UTC);p.completed_by=user_id;db.add(AuditLog(user_id=user_id,action='COMPLETE_PICKING',entity_type='PICKING',entity_id=p.id));db.commit();return p
def bol_read(b):
 return BOLRead.model_validate({**b.__dict__,'status_name':BOL_NAMES[b.status],'total_pallet_qty':sum((i.pallet_qty for i in b.items),Decimal(0)),'total_carton_qty':sum((i.carton_qty for i in b.items),Decimal(0)),'total_weight_lbs':sum((i.weight_lbs for i in b.items),Decimal(0)),'total_cbm':sum((i.cbm for i in b.items),Decimal(0)),'fc_address_missing':bool(b.amazon_fc_code and not b.ship_to_address)})
def generate_bol(db:Session,ob_id,user_id):
 o=get_ob(db,ob_id);if_not= db.scalar(select(BOL).where(BOL.outbound_order_id==ob_id));
 if if_not:return if_not
 w=o.warehouse;address=', '.join(x for x in (w.address,w.city,w.state,w.zip_code,w.country) if x);fba=o.fba_shipment;fcaddr=None
 if fba:fcaddr=fba.amazon_fc_address
 b=BOL(bol_no=number(db,BOL,'BOL'),outbound_order_id=ob_id,fba_shipment_id=o.fba_shipment_id,customer_id=o.customer_id,warehouse_id=o.warehouse_id,carrier_id=o.carrier_id,ship_from_name=w.warehouse_name,ship_from_address=address,ship_to_name=fcaddr.fc_name if fcaddr else None,ship_to_address=', '.join(x for x in (fcaddr.address_line1,fcaddr.city,fcaddr.state,fcaddr.zip_code) if x) if fcaddr else None,amazon_fc_code=o.fc_code or (fba.amazon_fc_code if fba else None),pickup_date=to_business_date(o.schedule_pickup_at),appointment_time=str(o.delivery_appointment_time) if o.delivery_appointment_time else None,status=BOLStatus.GENERATED,created_by=user_id);db.add(b);db.flush()
 for a in o.allocations:
  l=a.inventory_lot;b.items.append(BOLItem(outbound_allocation_id=a.id,inventory_lot_id=l.id,container_number=l.container_number,fc_code=l.fc_code,marking=l.marking,pallet_qty=a.allocated_pallet_qty-a.completed_pallet_qty,carton_qty=a.allocated_carton_qty-a.completed_carton_qty,weight_lbs=a.allocated_weight_lbs-a.completed_weight_lbs,cbm=a.allocated_cbm-a.completed_cbm,description='Outbound cargo'))
 db.add(AuditLog(user_id=user_id,action='CREATE_BOL',entity_type='BOL',entity_id=b.id));db.commit();return b
def bol_xlsx(b):
 wb=Workbook();ws=wb.active;ws.append(['BOL No','Outbound No','Ship From','Ship To','FC','Container','Pallet','Carton','Weight LBS','CBM']);
 for i in b.items:ws.append([b.bol_no,b.outbound.ob_no,b.ship_from_address,b.ship_to_address or '',b.amazon_fc_code,i.container_number,i.pallet_qty,i.carton_qty,i.weight_lbs,i.cbm])
 s=BytesIO();wb.save(s);return s.getvalue()
def bol_pdf(b):
 lines=[f'DLX Yuki WMS - BILL OF LADING',f'BOL No: {b.bol_no}',f'Outbound: {b.outbound.ob_no}',f'Ship From: {b.ship_from_name}, {b.ship_from_address}',f'Ship To: {b.ship_to_name or ""}, {b.ship_to_address or ""}','Items:']+[f'{i.container_number or ""} | {i.pallet_qty} PLT | {i.carton_qty} CTN | {i.weight_lbs} LBS | {i.cbm} CBM' for i in b.items];text='\\n'.join(lines);stream=f'BT /F1 10 Tf 40 760 Td ({text.replace(chr(10),") Tj 0 -16 Td (")}) Tj ET'.encode();return b'%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R>>endobj\n2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1>>endobj\n3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources<< /Font<< /F1 5 0 R>>>>>>endobj\n4 0 obj<< /Length '+str(len(stream)).encode()+b'>>stream\n'+stream+b'\nendstream endobj\n5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica>>endobj\ntrailer<< /Root 1 0 R>>\n%%EOF'
