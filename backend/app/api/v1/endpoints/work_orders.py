from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from app.api.deps import CurrentUser, DbSession, require_warehouse_write
from app.models import WorkOrder, WorkOrderEvent, WorkOrderPriority, WorkOrderStatus, WorkOrderType, User
from app.schemas.work_order import WorkOrderAssign, WorkOrderCreate, WorkOrderEventList, WorkOrderRead, WorkOrderStatusUpdate, WorkOrderUpdate
from app.services.work_order import create_work_order, get_work_order, read_event, read_work_order, transition_work_order, update_work_order
from app.services.access_policy import assert_warehouse_access, warehouse_clause

router=APIRouter(prefix='/work-orders',tags=['Work Orders'])
@router.get('',response_model=dict)
def list_work_orders(db:DbSession,user:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),q:str|None=None,status:WorkOrderStatus|None=None,work_order_type:WorkOrderType|None=None,warehouse_id:int|None=None,priority:WorkOrderPriority|None=None,assigned_to:int|None=None):
    filters=[]
    scope = warehouse_clause(user, WorkOrder.warehouse_id)
    if scope is not None: filters.append(scope)
    if q:filters.append(WorkOrder.work_order_no.ilike(f'%{q.strip()}%'))
    if status:filters.append(WorkOrder.status==status)
    if work_order_type:filters.append(WorkOrder.work_order_type==work_order_type)
    if warehouse_id:filters.append(WorkOrder.warehouse_id==warehouse_id)
    if priority:filters.append(WorkOrder.priority==priority)
    if assigned_to:filters.append(WorkOrder.assigned_to==assigned_to)
    rows=list(db.scalars(select(WorkOrder).where(*filters).order_by(WorkOrder.id.desc())).all());total=len(rows); rows=rows[(page-1)*per_page:page*per_page]
    return {'data':[read_work_order(x) for x in rows],'meta':{'page':page,'per_page':per_page,'total':total,'total_pages':(total+per_page-1)//per_page}}
@router.post('',response_model=WorkOrderRead,status_code=201)
def create(payload:WorkOrderCreate,db:DbSession,user:User=Depends(require_warehouse_write)):
    assert_warehouse_access(user,payload.warehouse_id); return read_work_order(create_work_order(db,payload,user.id))

def _scoped_work_order(db,user,work_order_id):
    stmt=select(WorkOrder).where(WorkOrder.id==work_order_id); scope=warehouse_clause(user,WorkOrder.warehouse_id)
    row=db.scalar(stmt.where(scope) if scope is not None else stmt)
    if row is None: raise HTTPException(404,"Work order not found")
    return get_work_order(db,row.id)
@router.get('/{work_order_id}',response_model=WorkOrderRead)
def detail(work_order_id:int,db:DbSession,user:CurrentUser):return read_work_order(_scoped_work_order(db,user,work_order_id))
@router.get('/{work_order_id}/events',response_model=WorkOrderEventList)
def events(work_order_id:int,db:DbSession,user:CurrentUser,order:str=Query('desc',pattern='^(asc|desc)$'),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    _scoped_work_order(db,user,work_order_id)
    total=db.scalar(select(func.count()).select_from(WorkOrderEvent).where(WorkOrderEvent.work_order_id==work_order_id)) or 0
    ordering=(WorkOrderEvent.created_at.asc(),WorkOrderEvent.id.asc()) if order=='asc' else (WorkOrderEvent.created_at.desc(),WorkOrderEvent.id.desc())
    rows=db.scalars(select(WorkOrderEvent).options(joinedload(WorkOrderEvent.actor)).where(WorkOrderEvent.work_order_id==work_order_id).order_by(*ordering).offset(offset).limit(limit)).all()
    return {'data':[read_event(row) for row in rows],'total':total,'limit':limit,'offset':offset}
@router.patch('/{work_order_id}',response_model=WorkOrderRead)
def update(work_order_id:int,payload:WorkOrderUpdate,db:DbSession,user:User=Depends(require_warehouse_write)):return read_work_order(update_work_order(db,_scoped_work_order(db,user,work_order_id),payload,user.id))
@router.post('/{work_order_id}/assign',response_model=WorkOrderRead)
def assign(work_order_id:int,payload:WorkOrderAssign,db:DbSession,user:User=Depends(require_warehouse_write)):return read_work_order(update_work_order(db,_scoped_work_order(db,user,work_order_id),payload,user.id))
@router.post('/{work_order_id}/status',response_model=WorkOrderRead)
def status(work_order_id:int,payload:WorkOrderStatusUpdate,db:DbSession,user:User=Depends(require_warehouse_write)):return read_work_order(transition_work_order(db,_scoped_work_order(db,user,work_order_id),payload.status,user.id))
