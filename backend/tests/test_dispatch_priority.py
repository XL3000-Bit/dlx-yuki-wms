from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import AuditLog, ContainerTracking, OutboundInventoryAllocation, OutboundOrder
from app.models.container_tracking import TrackingStatus
from app.models.outbound import OBStatus
from app.services.dispatch_priority import DispatchPriority, DispatchReadiness, calculate_dispatch_priority, calculate_dispatch_readiness
from tests.test_outbound import inventory, ob


def tracking(db: Session, container: str) -> ContainerTracking:
    value = ContainerTracking(container_number=container, source_fingerprint=f"fp-{container}", tracking_status=TrackingStatus.WAREHOUSE_RECEIVED)
    db.add(value); db.commit()
    return value


def scheduled_order(client: TestClient, seed, lot: dict, when: date, fc: str = "ONT8") -> dict:
    order = client.post('/api/v1/outbounds', json={**ob(seed), 'fc_code': fc, 'schedule_pickup_at': datetime.combine(when, datetime.min.time()).isoformat()}).json()
    response = client.post(f"/api/v1/outbounds/{order['id']}/allocate", json={'inventory_lot_id': lot['id'], 'pallet_qty': 1})
    assert response.status_code == 200, response.text
    return order


def prepare_dispatch(client: TestClient, outbound_id: int) -> None:
    picking = client.post(f"/api/v1/outbounds/{outbound_id}/picking-lists")
    assert picking.status_code == 200, picking.text
    completed = client.post(
        f"/api/v1/picking-lists/{picking.json()['id']}/complete",
        json={},
    )
    assert completed.status_code == 200, completed.text
    bol = client.post(f"/api/v1/outbounds/{outbound_id}/bol")
    assert bol.status_code == 200, bol.text


def test_priority_thresholds():
    today = date(2026, 8, 29)
    assert calculate_dispatch_priority(today - timedelta(days=1), today) == DispatchPriority.CRITICAL
    assert calculate_dispatch_priority(today, today) == DispatchPriority.CRITICAL
    assert calculate_dispatch_priority(today + timedelta(days=1), today) == DispatchPriority.HIGH
    assert calculate_dispatch_priority(today + timedelta(days=4), today) == DispatchPriority.MEDIUM
    assert calculate_dispatch_priority(today + timedelta(days=10), today) == DispatchPriority.NORMAL
    assert calculate_dispatch_priority(None, today) == DispatchPriority.NORMAL


def test_readiness_precedence_partial_shortage_and_terminal_states():
    base={'has_inventory':True,'has_allocation':True,'allocated_pallets':10,'available_inventory_pallets':10}
    assert calculate_dispatch_readiness(outbound_status=OBStatus.EXCEPTION,completed_pallets=10,**base)==DispatchReadiness.BLOCKED
    assert calculate_dispatch_readiness(outbound_status=OBStatus.COMPLETED,completed_pallets=10,**base)==DispatchReadiness.COMPLETED
    assert calculate_dispatch_readiness(outbound_status=OBStatus.IN_PROGRESS,completed_pallets=4,**base)==DispatchReadiness.PARTIAL
    assert calculate_dispatch_readiness(outbound_status=OBStatus.IN_PROGRESS,completed_pallets=0,**{**base,'available_inventory_pallets':5})==DispatchReadiness.NOT_READY
    assert calculate_dispatch_readiness(outbound_status=OBStatus.CANCELED,completed_pallets=0,**base)==DispatchReadiness.NOT_READY
    assert calculate_dispatch_readiness(outbound_status=OBStatus.NEW,has_inventory=True,has_allocation=False)==DispatchReadiness.NOT_READY
    assert calculate_dispatch_readiness(outbound_status=OBStatus.NEW,completed_pallets=0,**base)==DispatchReadiness.READY


def test_container_no_outbound_is_null(client: TestClient, db: Session):
    row = tracking(db, 'NO-OUTBOUND')
    body = client.get(f'/api/v1/container-tracking/{row.id}').json()['basic']
    assert body['earliest_outbound_date'] is None
    assert body['outbound_days_remaining'] is None


def test_earliest_outbound_ignores_canceled_and_updates(client: TestClient, db: Session, seed):
    container = 'FCIU9845101'; tracked = tracking(db, container); lot = inventory(client, seed, container=container, pallet=10)
    orders = [scheduled_order(client, seed, lot, date(2026, 8, 30), 'LAX9'), scheduled_order(client, seed, lot, date(2026, 8, 28), 'GYR2'), scheduled_order(client, seed, lot, date(2026, 9, 2), 'LAS1')]
    assert client.get('/api/v1/container-tracking').json()['data'][0]['earliest_outbound_date'] == '2026-08-28'
    detail = client.get(f'/api/v1/container-tracking/{tracked.id}').json()
    assert len(detail['related_outbound_tasks']) == 3
    assert client.post(f"/api/v1/outbounds/{orders[1]['id']}/cancel").status_code == 200
    assert client.get('/api/v1/container-tracking').json()['data'][0]['earliest_outbound_date'] == '2026-08-30'
    assert client.patch(f"/api/v1/outbounds/{orders[0]['id']}/schedule", json={'schedule_pickup_at': '2026-09-05T00:00:00'}).status_code == 200
    assert client.get('/api/v1/container-tracking').json()['data'][0]['earliest_outbound_date'] == '2026-09-02'
    assert db.query(AuditLog).filter(AuditLog.action=='UPDATE_OUTBOUND_SCHEDULE',AuditLog.entity_id==orders[0]['id']).count()==1


def test_completed_and_unscheduled_orders_do_not_set_earliest(client: TestClient, db: Session, seed):
    container='DONE-UNSCHEDULED';tracked=tracking(db,container);lot=inventory(client,seed,container=container,pallet=3)
    unscheduled=client.post('/api/v1/outbounds',json=ob(seed)).json();assert client.post(f"/api/v1/outbounds/{unscheduled['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':1}).status_code==200
    done=scheduled_order(client,seed,lot,date.today()+timedelta(days=1));assert client.post(f"/api/v1/outbounds/{done['id']}/confirm").status_code==200;prepare_dispatch(client,done['id']);assert client.post(f"/api/v1/outbounds/{done['id']}/dispatch").status_code==200;assert client.post(f"/api/v1/outbounds/{done['id']}/complete").status_code==200
    body=client.get(f'/api/v1/container-tracking/{tracked.id}').json()['basic'];assert body['earliest_outbound_date'] is None


def test_container_readiness_partial_and_blocked(client: TestClient, db: Session, seed):
    container='READY-STATES';tracked=tracking(db,container);lot=inventory(client,seed,container=container,pallet=10);order=scheduled_order(client,seed,lot,date.today()+timedelta(days=2));allocation=db.query(OutboundInventoryAllocation).filter_by(outbound_order_id=order['id']).one()
    partial=client.post(f"/api/v1/outbounds/{order['id']}/complete",json={'allocation_id':allocation.id,'pallet_qty':0.5});assert partial.status_code==200,partial.text
    assert client.get(f'/api/v1/container-tracking/{tracked.id}').json()['basic']['dispatch_readiness']=='PARTIAL'
    assert client.post(f"/api/v1/outbounds/{order['id']}/exception",json={'reason':'Inventory damage'}).status_code==200
    assert client.get(f'/api/v1/container-tracking/{tracked.id}').json()['basic']['dispatch_readiness']=='BLOCKED'


def test_container_not_completed_when_another_order_or_allocation_remains(client: TestClient, db: Session, seed):
    container='MULTI-DEMAND';tracked=tracking(db,container);lot=inventory(client,seed,container=container,pallet=10)
    completed_order=scheduled_order(client,seed,lot,date.today()+timedelta(days=1),'LAX9');active_order=scheduled_order(client,seed,lot,date.today()+timedelta(days=2),'GYR2')
    assert client.post(f"/api/v1/outbounds/{completed_order['id']}/confirm").status_code==200
    prepare_dispatch(client,completed_order['id'])
    assert client.post(f"/api/v1/outbounds/{completed_order['id']}/dispatch").status_code==200
    assert client.post(f"/api/v1/outbounds/{completed_order['id']}/complete").status_code==200
    assert client.get(f'/api/v1/container-tracking/{tracked.id}').json()['basic']['dispatch_readiness']=='PARTIAL'
    allocation=db.query(OutboundInventoryAllocation).filter_by(outbound_order_id=active_order['id']).one()
    assert client.post(f"/api/v1/outbounds/{active_order['id']}/complete",json={'allocation_id':allocation.id,'pallet_qty':0.5}).status_code==200
    assert client.get(f'/api/v1/container-tracking/{tracked.id}').json()['basic']['dispatch_readiness']=='PARTIAL'


def test_container_completed_and_canceled_boundary(client: TestClient, db: Session, seed):
    container='CANCEL-COMPLETE';tracked=tracking(db,container);lot=inventory(client,seed,container=container,pallet=5)
    canceled=scheduled_order(client,seed,lot,date.today()+timedelta(days=1));completed=scheduled_order(client,seed,lot,date.today()+timedelta(days=2))
    assert client.post(f"/api/v1/outbounds/{canceled['id']}/cancel").status_code==200
    assert client.post(f"/api/v1/outbounds/{completed['id']}/confirm").status_code==200
    prepare_dispatch(client,completed['id'])
    assert client.post(f"/api/v1/outbounds/{completed['id']}/dispatch").status_code==200
    assert client.post(f"/api/v1/outbounds/{completed['id']}/complete").status_code==200
    assert client.get(f'/api/v1/container-tracking/{tracked.id}').json()['basic']['dispatch_readiness']=='COMPLETED'
    only_canceled='ONLY-CANCELED';only_tracked=tracking(db,only_canceled);only_lot=inventory(client,seed,container=only_canceled,pallet=2);order=scheduled_order(client,seed,only_lot,date.today()+timedelta(days=1))
    assert client.post(f"/api/v1/outbounds/{order['id']}/cancel").status_code==200
    assert client.get(f'/api/v1/container-tracking/{only_tracked.id}').json()['basic']['dispatch_readiness']=='NOT_READY'


def test_completed_demand_is_not_reblocked_by_historical_exception(client: TestClient, db: Session, seed):
    container='DONE-EXCEPTION';tracked=tracking(db,container);lot=inventory(client,seed,container=container,pallet=2);order=scheduled_order(client,seed,lot,date.today()+timedelta(days=1));allocation=db.query(OutboundInventoryAllocation).filter_by(outbound_order_id=order['id']).one()
    prepare_dispatch(client,order['id'])
    assert client.post(f"/api/v1/outbounds/{order['id']}/complete",json={'allocation_id':allocation.id,'pallet_qty':1}).status_code==200
    assert client.post(f"/api/v1/outbounds/{order['id']}/exception",json={'reason':'Historical check'}).status_code==200
    assert client.get(f'/api/v1/container-tracking/{tracked.id}').json()['basic']['dispatch_readiness']=='COMPLETED'
    assert client.post(f"/api/v1/outbounds/{order['id']}/resolve-exception").status_code==200
    assert client.post(f"/api/v1/outbounds/{order['id']}/dispatch").status_code==200
    assert client.post(f"/api/v1/outbounds/{order['id']}/complete").status_code==200
    db.expire_all();assert db.get(OutboundOrder,order['id']).exception_reason=='Historical check'
    assert client.get(f'/api/v1/container-tracking/{tracked.id}').json()['basic']['dispatch_readiness']=='COMPLETED'


def test_multiple_fc_and_dispatch_filters(client: TestClient, db: Session, seed):
    container='MULTI-FC';tracking(db,container);lot=inventory(client,seed,container=container,pallet=4)
    scheduled_order(client,seed,lot,date.today()+timedelta(days=1),'LAX9');scheduled_order(client,seed,lot,date.today()+timedelta(days=2),'GYR2')
    body=client.get('/api/v1/container-tracking',params={'outbound_window':'next_3','dispatch_priority':'HIGH','sort_by':'dispatch_priority'}).json()
    assert body['meta']['total']==1 and body['data'][0]['container_number']==container


def test_container_list_uses_batched_aggregate(client: TestClient, db: Session, seed):
    for number in ('BATCH-Q1','BATCH-Q2'):
        tracking(db,number);lot=inventory(client,seed,container=number,pallet=2);scheduled_order(client,seed,lot,date.today()+timedelta(days=3))
    statements=[]
    def before_cursor_execute(*args):statements.append(args[2])
    event.listen(db.bind,'before_cursor_execute',before_cursor_execute)
    try:
        response=client.get('/api/v1/container-tracking',params={'per_page':100})
    finally:
        event.remove(db.bind,'before_cursor_execute',before_cursor_execute)
    assert response.status_code==200
    selects=[sql for sql in statements if sql.lstrip().upper().startswith('SELECT')]
    assert len(selects)<=3, selects
