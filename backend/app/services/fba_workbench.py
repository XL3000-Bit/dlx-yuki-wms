from app.services.history_policy import require_live_record, history_job_ids, HISTORY_LABEL
from datetime import date
from decimal import Decimal
from math import ceil
from statistics import mean
from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload
from app.core.config import settings
from app.models import (AmazonFCAddress, AuditLog, BOL, Customer, FBAInventoryAllocation, FBAShipment,
 InventoryLot, InventoryPriorityRule, OutboundOrder, PickingList, User, Warehouse)
from app.models.fba import FBAStatus
from app.models.outbound import OBStatus
from app.models.picking import PickingStatus
from app.models.user import UserRole
from app.services.fba import STATUS_NAMES, allocation_list, get_fba
from app.services.picking_bol import BOL_NAMES, PICK_NAMES, bol_read, picking_read
from app.services.outbound import read_ob, create_ob
from app.services.picking_bol import generate_bol, generate_picking
from app.schemas.outbound import OBCreate
from app.models.bol import BOLStatus
from app.services.dispatch_priority import ACTIVE_OUTBOUND_STATUSES, dispatch_fields
from app.utils.business_time import get_business_today
from app.services.access_policy import customer_clause, warehouse_clause

ZERO=Decimal(0); STAGE_NAMES={"waiting_picking":"Waiting Picking","waiting_appointment":"Waiting Appointment","waiting_outbound":"Waiting Outbound","dispatched":"Dispatched","completed":"Completed","exception":"Exception"}

def can_operate(user:User)->bool:return user.role in {UserRole.ADMIN,UserRole.MANAGER,UserRole.OUTBOUND,UserRole.WAREHOUSE}

def batch_action(db:Session,user:User,action:str,fba_ids:list[int]):
    results=[]
    for fba_id in dict.fromkeys(fba_ids):
        try:
            s=get_fba(db,fba_id,user=user)
            require_live_record(db,s)
            if s.status in (FBAStatus.CANCELED,FBAStatus.COMPLETED):
                results.append({'fba_id':fba_id,'status':'skipped','reason':'FBA is completed or canceled'});continue
            o=db.scalar(select(OutboundOrder).where(OutboundOrder.fba_shipment_id==fba_id,OutboundOrder.status.notin_([OBStatus.CANCELED,OBStatus.COMPLETED])).order_by(OutboundOrder.id.desc()))
            if action=='outbound':
                if o: results.append({'fba_id':fba_id,'status':'skipped','reason':'Active Outbound already exists','outbound_id':o.id});continue
                o=create_ob(db,OBCreate(customer_id=s.customer_id,warehouse_id=s.warehouse_id,carrier_id=s.carrier_id,fba_shipment_id=s.id,ob_type='FBA',schedule_pickup_at=s.scheduled_pickup_at,delivery_appointment_time=s.appointment_time,fc_code=s.amazon_fc_code,reference_no=s.reference_no),user.id)
                results.append({'fba_id':fba_id,'status':'successful','outbound_id':o.id});continue
            if not o:
                results.append({'fba_id':fba_id,'status':'skipped','reason':'No active Outbound'});continue
            if action=='picking':
                existing=db.scalar(select(PickingList).where(PickingList.outbound_order_id==o.id,PickingList.status!=PickingStatus.CANCELED).order_by(PickingList.id.desc()))
                if existing:results.append({'fba_id':fba_id,'status':'skipped','reason':'Picking List already exists','outbound_id':o.id,'picking_id':existing.id});continue
                p=generate_picking(db,o.id,user.id);results.append({'fba_id':fba_id,'status':'successful','outbound_id':o.id,'picking_id':p.id});continue
            if action=='bol':
                if db.scalar(select(BOL).where(BOL.outbound_order_id==o.id,BOL.status!=BOLStatus.CANCELED)):
                    b=db.scalar(select(BOL).where(BOL.outbound_order_id==o.id,BOL.status!=BOLStatus.CANCELED).order_by(BOL.id.desc()));results.append({'fba_id':fba_id,'status':'skipped','reason':'BOL already exists','outbound_id':o.id,'bol_id':b.id});continue
                if s.amazon_fc_address is None:results.append({'fba_id':fba_id,'status':'failed','reason':'Amazon FC address missing','outbound_id':o.id});continue
                b=generate_bol(db,o.id,user.id);results.append({'fba_id':fba_id,'status':'successful','outbound_id':o.id,'bol_id':b.id});continue
            results.append({'fba_id':fba_id,'status':'failed','reason':'Unsupported action'})
        except Exception as exc:
            db.rollback();results.append({'fba_id':fba_id,'status':'failed','reason':str(exc)[:240]})
    return {'action':action,'successful':sum(x['status']=='successful' for x in results),'skipped':sum(x['status']=='skipped' for x in results),'failed':sum(x['status']=='failed' for x in results),'results':results}

def resolve_workbench_stage(*,fba_status:int,outbound_status:int|None,picking_status:int|None,has_picking:bool,appointment_time,remaining:Decimal)->str:
    if fba_status==FBAStatus.HOLD or outbound_status==OBStatus.EXCEPTION or picking_status==PickingStatus.EXCEPTION:return "exception"
    if fba_status==FBAStatus.COMPLETED or outbound_status==OBStatus.COMPLETED:return "completed"
    if outbound_status==OBStatus.DISPATCHED:return "dispatched"
    if not has_picking and remaining>0:return "waiting_picking"
    if appointment_time is None:return "waiting_appointment"
    return "waiting_outbound"

def _rules(db):return list(db.scalars(select(InventoryPriorityRule).where(InventoryPriorityRule.is_active==True).order_by(InventoryPriorityRule.sort_order)).all())
def _priority(rules,aging):
    if aging is None:return None,None,None,0
    for r in rules:
        if aging>=r.min_days and(r.max_days is None or aging<=r.max_days):
            span=f"{r.min_days}d+" if r.max_days is None else f"{r.min_days}-{r.max_days}d";return r.priority_level,r.priority_label,span,r.sort_order
    return None,None,None,0

def _base_rows(db:Session,user:User,**p):
    alloc=select(FBAInventoryAllocation.fba_shipment_id.label('fid'),func.sum(FBAInventoryAllocation.allocated_pallet_qty).label('p'),func.sum(FBAInventoryAllocation.allocated_carton_qty).label('c'),func.sum(FBAInventoryAllocation.allocated_weight_lbs).label('w'),func.sum(FBAInventoryAllocation.allocated_cbm).label('v'),func.min(InventoryLot.inbound_date).label('oldest'),func.count(func.distinct(InventoryLot.container_number)).label('cc'),func.count(func.distinct(InventoryLot.location_id)).label('lc')).join(InventoryLot,InventoryLot.id==FBAInventoryAllocation.inventory_lot_id).group_by(FBAInventoryAllocation.fba_shipment_id).subquery()
    obmax=select(OutboundOrder.fba_shipment_id.label('fid'),func.max(OutboundOrder.id).label('oid')).where(OutboundOrder.fba_shipment_id.is_not(None)).group_by(OutboundOrder.fba_shipment_id).subquery()
    obdispatch=select(OutboundOrder.fba_shipment_id.label('fid'),func.min(OutboundOrder.schedule_pickup_at).label('earliest')).where(OutboundOrder.fba_shipment_id.is_not(None),OutboundOrder.status.in_(ACTIVE_OUTBOUND_STATUSES),OutboundOrder.schedule_pickup_at.is_not(None)).group_by(OutboundOrder.fba_shipment_id).subquery()
    pickmax=select(PickingList.outbound_order_id.label('oid'),func.max(PickingList.id).label('pid'),func.count(PickingList.id).label('pc')).group_by(PickingList.outbound_order_id).subquery()
    bolmax=select(BOL.outbound_order_id.label('oid'),func.max(BOL.id).label('bid')).group_by(BOL.outbound_order_id).subquery()
    q=select(FBAShipment,Customer.customer_name,Warehouse.warehouse_code,AmazonFCAddress.fc_name,alloc,obdispatch.c.earliest,OutboundOrder,PickingList,pickmax.c.pc,BOL).join(Warehouse,Warehouse.id==FBAShipment.warehouse_id).outerjoin(Customer,Customer.id==FBAShipment.customer_id).outerjoin(AmazonFCAddress,AmazonFCAddress.id==FBAShipment.amazon_fc_address_id).outerjoin(alloc,alloc.c.fid==FBAShipment.id).outerjoin(obdispatch,obdispatch.c.fid==FBAShipment.id).outerjoin(obmax,obmax.c.fid==FBAShipment.id).outerjoin(OutboundOrder,OutboundOrder.id==obmax.c.oid).outerjoin(pickmax,pickmax.c.oid==OutboundOrder.id).outerjoin(PickingList,PickingList.id==pickmax.c.pid).outerjoin(bolmax,bolmax.c.oid==OutboundOrder.id).outerjoin(BOL,BOL.id==bolmax.c.bid)
    filters=[]
    for scope in (warehouse_clause(user,FBAShipment.warehouse_id),customer_clause(user,FBAShipment.customer_id)):
        if scope is not None:filters.append(scope)
    if p.get('warehouse_id'):filters.append(FBAShipment.warehouse_id==p['warehouse_id'])
    if p.get('fba_ids'):filters.append(FBAShipment.id.in_(p['fba_ids']))
    if p.get('customer_id'):filters.append(FBAShipment.customer_id==p['customer_id'])
    if p.get('amazon_fc_code'):filters.append(FBAShipment.amazon_fc_code.ilike(f"%{p['amazon_fc_code']}%"))
    if p.get('carrier_id'):filters.append(FBAShipment.carrier_id==p['carrier_id'])
    if p.get('container_number'):filters.append(FBAShipment.allocations.any(FBAInventoryAllocation.inventory_lot.has(InventoryLot.container_number.ilike(f"%{p['container_number']}%"))))
    if p.get('location_id'):filters.append(FBAShipment.allocations.any(FBAInventoryAllocation.inventory_lot.has(InventoryLot.location_id==p['location_id'])))
    if p.get('st_number'):filters.append(FBAShipment.st_number.ilike(f"%{p['st_number']}%"))
    if p.get('po_number'):filters.append(FBAShipment.po_number.ilike(f"%{p['po_number']}%"))
    if p.get('fba_status') is not None:filters.append(FBAShipment.status==p['fba_status'])
    if p.get('outbound_status') is not None:filters.append(OutboundOrder.status==p['outbound_status'])
    if p.get('picking_status') is not None:filters.append(PickingList.status==p['picking_status'])
    if p.get('bol_status') is not None:filters.append(BOL.status==p['bol_status'])
    if p.get('scheduled_from'):filters.append(OutboundOrder.schedule_pickup_at>=p['scheduled_from'])
    if p.get('scheduled_to'):filters.append(OutboundOrder.schedule_pickup_at<=p['scheduled_to'])
    if p.get('appointment_from'):filters.append(OutboundOrder.delivery_appointment_time>=p['appointment_from'])
    if p.get('appointment_to'):filters.append(OutboundOrder.delivery_appointment_time<=p['appointment_to'])
    if p.get('priority'):pass
    if p.get('unload_from'):filters.append(alloc.c.oldest>=p['unload_from'])
    if p.get('unload_to'):filters.append(alloc.c.oldest<=p['unload_to'])
    if p.get('q'):
        t=f"%{p['q']}%";filters.append(or_(FBAShipment.fba_no.ilike(t),FBAShipment.amazon_fc_code.ilike(t),FBAShipment.shipment_id.ilike(t),FBAShipment.st_number.ilike(t),FBAShipment.po_number.ilike(t),FBAShipment.reference_no.ilike(t),OutboundOrder.ob_no.ilike(t),PickingList.picking_no.ilike(t),BOL.bol_no.ilike(t),FBAShipment.allocations.any(FBAInventoryAllocation.inventory_lot.has(or_(InventoryLot.container_number.ilike(t),InventoryLot.fc_code.ilike(t),InventoryLot.lot_no.ilike(t))))))
    q=q.where(*filters)
    if db.bind and db.bind.dialect.name=='postgresql':
        aging=literal(get_business_today())-alloc.c.oldest
        priority=case(*[(aging>=r.min_days, r.sort_order) for r in _rules(db)],else_=0)
        sort_map={'priority_rank':priority,'max_aging_days':aging,'oldest_inbound_date':alloc.c.oldest,'fba_no':FBAShipment.fba_no,'amazon_fc_code':FBAShipment.amazon_fc_code,'total_pallet_qty':alloc.c.p,'total_carton_qty':alloc.c.c,'total_weight_lbs':alloc.c.w,'total_cbm':alloc.c.v,'appointment_time':func.coalesce(OutboundOrder.delivery_appointment_time,FBAShipment.appointment_time),'created_at':FBAShipment.created_at}
        sort=sort_map.get(p.get('sort_by','priority_rank'),priority);q=q.order_by((sort.desc() if p.get('sort_order','desc')!='asc' else sort.asc()).nulls_last(),FBAShipment.id.desc())
    return db.execute(q).all()

def list_workbench(db:Session,user:User,**p):
    rules=_rules(db);rows=[]
    history_ids=history_job_ids(db)
    for s,customer,warehouse,fc_name,fid,pal,cart,weight,cbm,oldest,cc,lc,earliest,o,pk,pc,b in _base_rows(db,user,**p):
        aging=max(0,(get_business_today()-oldest).days)if oldest else None;level,label,span,rank=_priority(rules,aging);remaining=Decimal(pal or 0)
        stage=resolve_workbench_stage(fba_status=s.status,outbound_status=o.status if o else None,picking_status=pk.status if pk else None,has_picking=bool(pc),appointment_time=(o.delivery_appointment_time if o else s.appointment_time),remaining=remaining)
        rows.append(dict(id=s.id,fba_no=s.fba_no,shipment_id=s.shipment_id,st_number=s.st_number,po_number=s.po_number,reference_no=s.reference_no,customer_id=s.customer_id,customer=customer,warehouse_id=s.warehouse_id,warehouse=warehouse,carrier='',amazon_fc_code=s.amazon_fc_code,amazon_fc_name=fc_name,fc_address_missing=s.amazon_fc_address_id is None,container_count=cc or 0,containers_preview=[],location_count=lc or 0,locations_preview=[],total_pallet_qty=pal or ZERO,total_carton_qty=cart or ZERO,total_weight_lbs=weight or ZERO,total_cbm=cbm or ZERO,oldest_inbound_date=oldest,max_aging_days=aging,priority_level=level,priority_label=label,priority_range=span,priority_rank=rank,**dispatch_fields(earliest,oldest),appointment_time=o.delivery_appointment_time if o else s.appointment_time,scheduled_pickup_at=o.schedule_pickup_at if o else s.scheduled_pickup_at,picking_count=pc or 0,picking_id=pk.id if pk else None,picking_no=pk.picking_no if pk else None,picking_status=pk.status if pk else None,bol_id=b.id if b else None,bol_no=b.bol_no if b else None,bol_status=b.status if b else None,outbound_id=o.id if o else None,outbound_no=o.ob_no if o else None,outbound_status=o.status if o else None,workbench_stage=stage,workbench_stage_name=HISTORY_LABEL if s.import_job_id in history_ids else STAGE_NAMES[stage],has_exception=stage=='exception',status=s.status,created_at=s.created_at,updated_at=s.updated_at))
    attention=min((x.min_days for x in rules if x.min_days>0),default=8)
    if p.get('priority'):rows=[x for x in rows if x['priority_level']==p['priority']]
    if p.get('aging_min') is not None:rows=[x for x in rows if x['max_aging_days'] is not None and x['max_aging_days']>=p['aging_min']]
    if p.get('aging_max') is not None:rows=[x for x in rows if x['max_aging_days'] is not None and x['max_aging_days']<=p['aging_max']]
    if p.get('only_old'):rows=[x for x in rows if(x['max_aging_days']or 0)>=attention]
    counts={'all':len(rows),'waiting_picking':0,'waiting_appointment':0,'waiting_outbound':0,'dispatched':0,'completed':0,'exception':0}
    for r in rows:counts[r['workbench_stage']]+=1
    if p.get('stage')and p['stage']!='all':rows=[x for x in rows if x['workbench_stage']==p['stage']]
    summary={'task_count':len(rows),'total_pallet_qty':sum((x['total_pallet_qty']for x in rows),ZERO),'total_carton_qty':sum((x['total_carton_qty']for x in rows),ZERO),'total_weight_lbs':sum((x['total_weight_lbs']for x in rows),ZERO),'total_cbm':sum((x['total_cbm']for x in rows),ZERO),'average_aging_days':Decimal(str(round(mean([x['max_aging_days']for x in rows if x['max_aging_days']is not None]),2)))if any(x['max_aging_days']is not None for x in rows)else None}
    sort=p.get('sort_by')or'priority_rank';reverse=p.get('sort_order','desc')!='asc'
    if not(db.bind and db.bind.dialect.name=='postgresql'):rows.sort(key=lambda x:(x.get(sort)is not None,x.get(sort)or 0,x['max_aging_days']or 0,-x['id']),reverse=reverse)
    page=p.get('page',1);per=p.get('per_page',20);total=len(rows);page_rows=rows[(page-1)*per:page*per]
    ids=[x['id']for x in page_rows]
    if ids:
        previews=db.execute(select(FBAInventoryAllocation.fba_shipment_id,InventoryLot.container_number,InventoryLot.raw_location_text).join(InventoryLot,InventoryLot.id==FBAInventoryAllocation.inventory_lot_id).where(FBAInventoryAllocation.fba_shipment_id.in_(ids))).all();by={i:(set(),set())for i in ids}
        for fid,container,location in previews:
            by[fid][0].add(container)
            if location:by[fid][1].update(x.strip()for x in location.split(',')if x.strip())
        for x in page_rows:x['containers_preview']=sorted(by[x['id']][0])[:5];x['locations_preview']=sorted(by[x['id']][1])[:8];x['location_count']=max(x['location_count'],len(by[x['id']][1]))
    return {'data':page_rows,'meta':{'page':page,'per_page':per,'total':total,'total_pages':ceil(total/per)if total else 0,'attention_threshold_days':attention,'trailer_default_pallet_capacity':settings.trailer_default_pallet_capacity},'summary':summary,'stage_counts':counts,'permissions':{'can_export':True,'can_operate':can_operate(user)}}

def workbench_detail(db:Session,fba_id:int,user:User):
    s=get_fba(db,fba_id,user=user);alloc=[x.model_dump(mode='json')for x in allocation_list(db,s)];o=db.scalar(select(OutboundOrder).options(joinedload(OutboundOrder.warehouse),joinedload(OutboundOrder.customer),joinedload(OutboundOrder.carrier),selectinload(OutboundOrder.allocations)).where(OutboundOrder.fba_shipment_id==fba_id).order_by(OutboundOrder.id.desc()).limit(1));picks=list(db.scalars(select(PickingList).options(selectinload(PickingList.items)).where(PickingList.outbound_order_id==o.id).order_by(PickingList.id.desc())).all())if o else[];bol=db.scalar(select(BOL).options(selectinload(BOL.items),joinedload(BOL.outbound)).where(BOL.outbound_order_id==o.id).order_by(BOL.id.desc()).limit(1))if o else None
    stage=resolve_workbench_stage(fba_status=s.status,outbound_status=o.status if o else None,picking_status=picks[0].status if picks else None,has_picking=bool(picks),appointment_time=o.delivery_appointment_time if o else s.appointment_time,remaining=sum((a.allocated_pallet_qty for a in s.allocations),ZERO));ids=[fba_id]+([o.id]if o else[])+([x.id for x in picks])+([bol.id]if bol else[]);audits=db.execute(select(AuditLog,User.display_name).outerjoin(User,User.id==AuditLog.user_id).where(AuditLog.entity_id.in_(ids)).order_by(AuditLog.created_at.desc()).limit(100)).all()
    workflow=[{'key':'fba','label':'FBA Linked','status':'completed'},{'key':'picking','label':'Picking','status':'completed'if picks else('exception'if stage=='exception'else'current')},{'key':'bol','label':'BOL','status':'completed'if bol else('current'if picks else'pending')},{'key':'appointment','label':'Appointment','status':'completed'if(o and o.delivery_appointment_time)else('current'if bol else'pending')},{'key':'outbound','label':'Outbound','status':'completed'if(o and o.status in (OBStatus.DISPATCHED,OBStatus.COMPLETED))else('current'if o and o.delivery_appointment_time else'pending')}]
    history_ids=history_job_ids(db)
    basic={'id':s.id,'fba_no':s.fba_no,'internal_fba_no':s.fba_no,'customer':s.customer.customer_name if s.customer else None,'warehouse':s.warehouse.warehouse_code,'amazon_fc_code':s.amazon_fc_code,'amazon_fc_name':s.amazon_fc_address.fc_name if s.amazon_fc_address else None,'amazon_fc_address':(', '.join(filter(None,[s.amazon_fc_address.address_line1,s.amazon_fc_address.city,s.amazon_fc_address.state,s.amazon_fc_address.zip_code]))if s.amazon_fc_address else None),'fc_address_missing':s.amazon_fc_address is None,'shipment_id':s.shipment_id,'st_number':s.st_number,'po_number':s.po_number,'reference_no':s.reference_no,'scheduled_pickup_at':o.schedule_pickup_at if o else s.scheduled_pickup_at,'appointment_time':o.delivery_appointment_time if o else s.appointment_time,'carrier':(o.carrier.carrier_name if o and o.carrier else(s.carrier.carrier_name if s.carrier else None)),'status':s.status,'status_name':STATUS_NAMES[s.status],'workbench_stage':stage,'workbench_stage_name':HISTORY_LABEL if s.import_job_id in history_ids else STAGE_NAMES[stage],'created_by':s.creator.display_name,'created_at':s.created_at,'remark':s.remark}
    return {'basic':basic,'inventory_sources':alloc,'picking':[picking_read(x).model_dump(mode='json')for x in picks],'bol':bol_read(bol).model_dump(mode='json')if bol else None,'outbound':read_ob(db,o).model_dump(mode='json')if o else None,'audit':[{'time':a.created_at,'user':name or'绯荤粺','action':a.action,'entity':a.entity_type,'detail':a.after_data or a.before_data}for a,name in audits],'workflow':workflow,'permissions':{'can_export':True,'can_operate':can_operate(user)and s.import_job_id not in history_ids and stage not in('dispatched','completed')}}



