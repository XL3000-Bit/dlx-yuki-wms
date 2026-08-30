from datetime import date, datetime, timezone
from sqlalchemy import func, select
from fastapi import HTTPException
from app.models import ContainerTracking, Load, LoadStatus, OutboundOrder, PickingList, User, Warehouse, WorkOrderEvent
from app.models.work_order import WorkOrder, WorkOrderPriority, WorkOrderStatus, WorkOrderType

TRANSITIONS={WorkOrderStatus.OPEN:{WorkOrderStatus.ASSIGNED,WorkOrderStatus.IN_PROGRESS,WorkOrderStatus.CANCELED},WorkOrderStatus.ASSIGNED:{WorkOrderStatus.IN_PROGRESS,WorkOrderStatus.CANCELED},WorkOrderStatus.IN_PROGRESS:{WorkOrderStatus.COMPLETED},WorkOrderStatus.COMPLETED:set(),WorkOrderStatus.CANCELED:set()}
def generate_work_order_no(db,today:date|None=None):
    day=today or date.today(); prefix=f'WO-{day:%Y%m%d}-'; last=db.scalar(select(func.max(WorkOrder.work_order_no)).where(WorkOrder.work_order_no.like(prefix+'%'))); return f'{prefix}{(int(last[-4:])+1 if last else 1):04d}'
def _enum(enum_type,value,label):
    try:return enum_type(str(value).upper())
    except ValueError as exc:raise HTTPException(422,f'Invalid {label}') from exc
def _validate_refs(db,p):
    wh=db.get(Warehouse,p.warehouse_id)
    if not wh:raise HTTPException(422,'Warehouse not found')
    load=db.get(Load,p.load_id) if p.load_id else None; ob=db.get(OutboundOrder,p.outbound_id) if p.outbound_id else None; pick=db.get(PickingList,p.picking_list_id) if p.picking_list_id else None; container=db.get(ContainerTracking,p.container_tracking_id) if p.container_tracking_id else None
    if p.load_id and not load:raise HTTPException(404,'Load not found')
    if p.outbound_id and not ob:raise HTTPException(404,'Outbound order not found')
    if p.picking_list_id and not pick:raise HTTPException(404,'Picking list not found')
    if p.container_tracking_id and not container:raise HTTPException(404,'Container tracking not found')
    if load and (load.warehouse_id!=p.warehouse_id or load.status in (LoadStatus.COMPLETED,LoadStatus.CANCELED)):raise HTTPException(409,'Load is invalid for this work order')
    if ob and (ob.warehouse_id!=p.warehouse_id or ob.status in (5,6)):raise HTTPException(409,'Outbound order is invalid for this work order')
    if pick and ob and pick.outbound_order_id!=ob.id:raise HTTPException(409,'Picking list does not belong to outbound order')
    if pick and not ob: ob=db.get(OutboundOrder,pick.outbound_order_id)
    if ob and ob.warehouse_id!=p.warehouse_id:raise HTTPException(409,'Related outbound warehouse differs')
    if container and container.warehouse_id and container.warehouse_id!=p.warehouse_id:raise HTTPException(409,'Container warehouse differs')
    return load,ob,pick,container
def create_work_order(db,p,user_id):
    _validate_refs(db,p); data=p.model_dump(); data['work_order_type']=_enum(WorkOrderType,data.pop('work_order_type'),'work order type'); data['priority']=_enum(WorkOrderPriority,data['priority'],'priority'); data['created_by']=user_id
    assigned=data.get('assigned_to');
    if assigned and not db.get(User,assigned):raise HTTPException(422,'Assignee not found')
    wo=WorkOrder(work_order_no=generate_work_order_no(db),**data); db.add(wo); db.flush(); db.add(WorkOrderEvent(work_order_id=wo.id,event_type='CREATED',actor_user_id=user_id,assigned_to_after=wo.assigned_to,assigned_team_after=wo.assigned_team,priority_after=wo.priority.value,note=wo.notes)); db.commit(); return get_work_order(db,wo.id)
def get_work_order(db,id):
    wo=db.get(WorkOrder,id)
    if not wo:raise HTTPException(404,'Work order not found')
    return wo
def update_work_order(db,wo,p,user_id):
    if wo.status in (WorkOrderStatus.COMPLETED,WorkOrderStatus.CANCELED):raise HTTPException(409,'Terminal work order is immutable')
    data=p.model_dump(exclude_unset=True); before={k:getattr(wo,k) for k in ('assigned_to','assigned_team','priority','scheduled_at','notes')}
    if 'priority' in data and data['priority'] is not None:data['priority']=_enum(WorkOrderPriority,data['priority'],'priority')
    if 'assigned_to' in data and data['assigned_to'] and not db.get(User,data['assigned_to']):raise HTTPException(422,'Assignee not found')
    for k,v in data.items():setattr(wo,k,v)
    if 'assigned_to' in data or 'assigned_team' in data:
        db.add(WorkOrderEvent(work_order_id=wo.id,event_type='ASSIGNED' if before['assigned_to'] is None and before['assigned_team'] is None else 'REASSIGNED',actor_user_id=user_id,assigned_to_before=before['assigned_to'],assigned_to_after=wo.assigned_to,assigned_team_before=before['assigned_team'],assigned_team_after=wo.assigned_team))
    if 'priority' in data and before['priority'] != wo.priority: db.add(WorkOrderEvent(work_order_id=wo.id,event_type='PRIORITY_CHANGED',actor_user_id=user_id,priority_before=before['priority'].value,priority_after=wo.priority.value))
    if 'scheduled_at' in data and before['scheduled_at'] != wo.scheduled_at: db.add(WorkOrderEvent(work_order_id=wo.id,event_type='SCHEDULE_CHANGED',actor_user_id=user_id,note=f'{before["scheduled_at"]} → {wo.scheduled_at}'))
    if 'notes' in data and before['notes'] != wo.notes: db.add(WorkOrderEvent(work_order_id=wo.id,event_type='NOTE_UPDATED',actor_user_id=user_id,note=wo.notes))
    db.commit();return get_work_order(db,wo.id)
def transition_work_order(db,wo,target,user_id):
    status=_enum(WorkOrderStatus,target,'work order status')
    if status not in TRANSITIONS[wo.status]:raise HTTPException(409,f'Invalid status transition: {wo.status.value} to {status.value}')
    old=wo.status; wo.status=status; now=datetime.now(timezone.utc)
    if status==WorkOrderStatus.IN_PROGRESS:wo.started_at=now
    if status==WorkOrderStatus.COMPLETED:wo.completed_at=now
    db.add(WorkOrderEvent(work_order_id=wo.id,event_type='STATUS_CHANGED',actor_user_id=user_id,from_status=old.value,to_status=status.value)); db.commit();return get_work_order(db,wo.id)
def read_work_order(wo):return {**{k:getattr(wo,k) for k in ('id','work_order_no','work_order_type','status','warehouse_id','load_id','outbound_id','picking_list_id','container_tracking_id','priority','assigned_to','assigned_team','scheduled_at','started_at','completed_at','notes','created_by','created_at','updated_at')},'work_order_type':wo.work_order_type.value,'status':wo.status.value,'priority':wo.priority.value,'assignee_name':wo.assignee.display_name if wo.assignee else None}
def read_event(event):return {'id':event.id,'event_type':event.event_type,'from_status':event.from_status,'to_status':event.to_status,'actor_user_id':event.actor_user_id,'actor_name':event.actor.display_name if event.actor else None,'assigned_to_before':event.assigned_to_before,'assigned_to_after':event.assigned_to_after,'assigned_team_before':event.assigned_team_before,'assigned_team_after':event.assigned_team_after,'priority_before':event.priority_before,'priority_after':event.priority_after,'note':event.note,'created_at':event.created_at}
