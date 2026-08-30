from typing import Annotated
from datetime import date,timedelta
from fastapi import APIRouter,UploadFile,File,Depends,Query,HTTPException
from sqlalchemy import select,or_,func
from sqlalchemy.orm import Session
from app.api.deps import CurrentUser,DbSession,require_warehouse_write
from app.models import BOL,ContainerTracking,InboundRecord,InventoryLot,OutboundInventoryAllocation,OutboundOrder,PickingList,User
from app.models.outbound import OBStatus
from app.services.container_tracking import import_csv
from app.services.dispatch_priority import ACTIVE_OUTBOUND_STATUSES,container_dispatch_aggregate,dispatch_fields,calculate_dispatch_readiness
from app.services.access_policy import customer_clause, warehouse_clause
from app.utils.business_time import business_day_range,get_business_today,to_business_date
router=APIRouter(prefix='/container-tracking',tags=['Container Tracking']);Writer=Annotated[User,Depends(require_warehouse_write)]
@router.post('/import')
async def import_tracking(db:DbSession,user:Writer,file:UploadFile=File(...)):return import_csv(db,await file.read(),file.filename or 'shipmentexport.csv',user)
@router.get('')
def listing(db:DbSession,user:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),q:str|None=None,status:str|None=None,warehouse_id:int|None=None,outbound_window:str|None=None,outbound_from:date|None=None,outbound_to:date|None=None,dispatch_priority:str|None=None,sort_by:str='pod_eta',sort_order:str='desc'):
 agg=container_dispatch_aggregate(user);query=select(ContainerTracking,agg).outerjoin(agg,func.upper(agg.c.container_number)==func.upper(ContainerTracking.container_number));filters=[]
 scope=warehouse_clause(user,ContainerTracking.warehouse_id)
 if scope is not None:filters.append(scope)
 if q:
  t=f'%{q}%';filters.append(or_(ContainerTracking.container_number.ilike(t),ContainerTracking.mbl_number.ilike(t),ContainerTracking.hbl_number.ilike(t),ContainerTracking.customer_reference.ilike(t),ContainerTracking.delivery_warehouse_raw.ilike(t)))
 if status:filters.append(ContainerTracking.tracking_status==status)
 if warehouse_id:filters.append(ContainerTracking.warehouse_id==warehouse_id)
 today=get_business_today();start=end=None
 if outbound_window=='overdue':end=today-timedelta(days=1)
 elif outbound_window=='today':start=end=today
 elif outbound_window=='tomorrow':start=end=today+timedelta(days=1)
 elif outbound_window=='next_3':start=today;end=today+timedelta(days=3)
 elif outbound_window=='next_7':start=today;end=today+timedelta(days=7)
 elif outbound_window=='none':filters.append(agg.c.earliest_outbound_at.is_(None))
 start=outbound_from or start;end=outbound_to or end
 if start:filters.append(agg.c.earliest_outbound_at>=business_day_range(start)[0])
 if end:filters.append(agg.c.earliest_outbound_at<business_day_range(end)[1])
 raw=db.execute(query.where(*filters)).all();items=[row(r,earliest,inbound) for r,_,earliest,inbound,_,_ in raw]
 if dispatch_priority:items=[x for x in items if x['dispatch_priority']==dispatch_priority.upper()]
 keys={'earliest_outbound_date':'earliest_outbound_date','outbound_days_remaining':'outbound_days_remaining','warehouse_days':'warehouse_days','dispatch_priority':'dispatch_priority_rank','pod_eta':'pod_eta'};key=keys.get(sort_by,'pod_eta');reverse=sort_order!='asc'
 items.sort(key=lambda x:(x.get(key) is not None,x.get(key) if x.get(key) is not None else 0),reverse=reverse);total=len(items);items=items[(page-1)*per_page:page*per_page]
 return {'data':items,'meta':{'page':page,'per_page':per_page,'total':total,'total_pages':(total+per_page-1)//per_page}}
def row(r,earliest=None,inbound_date=None):return {'id':r.id,'container_number':r.container_number,'mbl_number':r.mbl_number,'hbl_number':r.hbl_number,'pod_eta':r.pod_eta,'ir_eta':r.ir_eta,'pod':r.pod,'delivery_location':r.delivery_location,'delivery_warehouse_raw':r.delivery_warehouse_raw,'scheduled_delivery_at':r.scheduled_delivery_at,'actual_delivery_at':r.actual_delivery_at,'wa_received_at':r.wa_received_at,'wa_empty_at':r.wa_empty_at,'wa_complete_at':r.wa_complete_at,'tracking_status':r.tracking_status.value,'is_received':r.wa_received_at is not None,'is_empty':r.wa_empty_at is not None,'is_complete':r.wa_complete_at is not None,'anomalies':[],'source_file_name':r.source_file_name,'source_row_number':r.source_row_number,**dispatch_fields(earliest,inbound_date)}
@router.get('/{tracking_id}')
def detail(tracking_id:int,db:DbSession,user:CurrentUser):
 stmt=select(ContainerTracking).where(ContainerTracking.id==tracking_id);scope=warehouse_clause(user,ContainerTracking.warehouse_id)
 r=db.scalar(stmt.where(scope) if scope is not None else stmt)
 if not r:raise HTTPException(404,'Container tracking not found')
 link_stmt=select(InboundRecord).where(func.upper(InboundRecord.container_number)==r.container_number.upper());lot_stmt=select(InventoryLot).where(func.upper(InventoryLot.container_number)==r.container_number.upper())
 for scope in (warehouse_clause(user,InboundRecord.warehouse_id),customer_clause(user,InboundRecord.customer_id)):
  if scope is not None:link_stmt=link_stmt.where(scope)
 for scope in (warehouse_clause(user,InventoryLot.warehouse_id),customer_clause(user,InventoryLot.customer_id)):
  if scope is not None:lot_stmt=lot_stmt.where(scope)
 links=list(db.scalars(link_stmt).all());agg=container_dispatch_aggregate(user);d=db.execute(select(agg).where(func.upper(agg.c.container_number)==r.container_number.upper())).first();earliest=d.earliest_outbound_at if d else None;inbound=d.inbound_date if d else min((x.received_date or x.unload_date for x in links if x.received_date or x.unload_date),default=None)
 lots=list(db.scalars(lot_stmt).all())
 task_stmt=select(OutboundOrder,OutboundInventoryAllocation,InventoryLot).join(OutboundInventoryAllocation,OutboundInventoryAllocation.outbound_order_id==OutboundOrder.id).join(InventoryLot,InventoryLot.id==OutboundInventoryAllocation.inventory_lot_id).where(func.upper(InventoryLot.container_number)==r.container_number.upper(),OutboundOrder.status!=OBStatus.CANCELED)
 for scope in (warehouse_clause(user,OutboundOrder.warehouse_id),customer_clause(user,OutboundOrder.customer_id)):
  if scope is not None:task_stmt=task_stmt.where(scope)
 tasks=db.execute(task_stmt.order_by(OutboundOrder.schedule_pickup_at.asc().nullslast())).all();related=[]
 order_ids={o.id for o,_,_ in tasks};pickings=list(db.scalars(select(PickingList).where(PickingList.outbound_order_id.in_(order_ids)).order_by(PickingList.id)).all()) if order_ids else[];bols=list(db.scalars(select(BOL).where(BOL.outbound_order_id.in_(order_ids)).order_by(BOL.id)).all()) if order_ids else[];picking_by_order={x.outbound_order_id:x for x in pickings};bol_by_order={x.outbound_order_id:x for x in bols}
 for o,a,l in tasks:
  picking=picking_by_order.get(o.id);bol=bol_by_order.get(o.id);related.append({'outbound_id':o.id,'ob_no':o.ob_no,'fc_code':o.fc_code or l.fc_code,'outbound_date':to_business_date(o.schedule_pickup_at),'pallet_qty':a.allocated_pallet_qty,'completed_pallet_qty':a.completed_pallet_qty,'status':o.status,'status_name':OBStatus(o.status).name,'picking_status':picking.status if picking else None,'bol_id':bol.id if bol else None,'bol_no':bol.bol_no if bol else None,'bol_status':bol.status if bol else None})
 allocated=sum((a.allocated_pallet_qty for _,a,_ in tasks),0);completed=sum((a.completed_pallet_qty for _,a,_ in tasks),0);active=[(o,a)for o,a,_ in tasks if o.status not in(OBStatus.CANCELED,OBStatus.COMPLETED)and a.allocated_pallet_qty>a.completed_pallet_qty]
 readiness_status=OBStatus.EXCEPTION if any(o.status==OBStatus.EXCEPTION for o,a in active) else OBStatus.COMPLETED if tasks and not active else active[0][0].status if active else None;capacity=sum((x.available_pallet_qty+x.allocated_pallet_qty for x in lots),0)
 basic=row(r,earliest,inbound);basic['dispatch_readiness']=calculate_dispatch_readiness(outbound_status=readiness_status,has_inventory=bool(lots)and capacity>0,has_allocation=bool(tasks),allocated_pallets=allocated,completed_pallets=completed,available_inventory_pallets=capacity).value
 return {'basic':basic,'inbound':[{'id':x.id,'fc_code':x.fc_code,'pallet_qty':x.pallet_qty,'carton_qty':x.carton_qty,'weight_lbs':x.weight_lbs,'cbm':x.cbm} for x in links],'inventory_lots':[{'id':x.id,'lot_no':x.lot_no,'status':x.status,'available_pallet_qty':x.available_pallet_qty,'allocated_pallet_qty':x.allocated_pallet_qty}for x in lots],'related_outbound_tasks':related,'anomalies':[]}
