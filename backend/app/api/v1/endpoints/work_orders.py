from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from app.api.deps import CurrentUser, DbSession, require_warehouse_write
from app.models import WorkOrder, WorkOrderPriority, WorkOrderStatus, WorkOrderType, User
from app.schemas.work_order import WorkOrderCreate, WorkOrderRead, WorkOrderStatusUpdate, WorkOrderUpdate
from app.services.work_order import create_work_order, get_work_order, read_work_order, transition_work_order, update_work_order

router=APIRouter(prefix='/work-orders',tags=['Work Orders'])
@router.get('',response_model=dict)
def list_work_orders(db:DbSession,_:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),q:str|None=None,status:WorkOrderStatus|None=None,work_order_type:WorkOrderType|None=None,warehouse_id:int|None=None,priority:WorkOrderPriority|None=None,assigned_to:int|None=None):
    filters=[]
    if q:filters.append(WorkOrder.work_order_no.ilike(f'%{q.strip()}%'))
    if status:filters.append(WorkOrder.status==status)
    if work_order_type:filters.append(WorkOrder.work_order_type==work_order_type)
    if warehouse_id:filters.append(WorkOrder.warehouse_id==warehouse_id)
    if priority:filters.append(WorkOrder.priority==priority)
    if assigned_to:filters.append(WorkOrder.assigned_to==assigned_to)
    rows=list(db.scalars(select(WorkOrder).where(*filters).order_by(WorkOrder.id.desc())).all());total=len(rows); rows=rows[(page-1)*per_page:page*per_page]
    return {'data':[read_work_order(x) for x in rows],'meta':{'page':page,'per_page':per_page,'total':total,'total_pages':(total+per_page-1)//per_page}}
@router.post('',response_model=WorkOrderRead,status_code=201)
def create(payload:WorkOrderCreate,db:DbSession,user:User=Depends(require_warehouse_write)):return read_work_order(create_work_order(db,payload,user.id))
@router.get('/{work_order_id}',response_model=WorkOrderRead)
def detail(work_order_id:int,db:DbSession,_:CurrentUser):return read_work_order(get_work_order(db,work_order_id))
@router.patch('/{work_order_id}',response_model=WorkOrderRead)
def update(work_order_id:int,payload:WorkOrderUpdate,db:DbSession,user:User=Depends(require_warehouse_write)):return read_work_order(update_work_order(db,get_work_order(db,work_order_id),payload))
@router.post('/{work_order_id}/status',response_model=WorkOrderRead)
def status(work_order_id:int,payload:WorkOrderStatusUpdate,db:DbSession,user:User=Depends(require_warehouse_write)):return read_work_order(transition_work_order(db,get_work_order(db,work_order_id),payload.status))
