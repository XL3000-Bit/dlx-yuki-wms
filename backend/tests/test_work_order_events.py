from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app


def create_work_order(client, seed):
    response = client.post('/api/v1/work-orders', json={'work_order_type':'GENERAL','warehouse_id':seed['warehouse'].id})
    assert response.status_code == 201
    return response.json()


def events(client, work_order_id, **params):
    response = client.get(f'/api/v1/work-orders/{work_order_id}/events', params=params)
    assert response.status_code == 200
    return response.json()


def test_creation_event_shape_actor_timestamp_auth_and_existence(client, seed):
    work_order = create_work_order(client, seed)
    payload = events(client, work_order['id'])
    assert payload['total'] == 1
    event = payload['data'][0]
    assert event['event_type'] == 'WORK_ORDER_CREATED'
    assert event['old_value'] is None and event['new_value'] == work_order['work_order_no']
    assert event['actor'] == {'id':seed['admin'].id,'username':'admin','display_name':'Admin'}
    assert event['actor_name'] == 'Admin'
    datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))
    assert TestClient(app).get(f"/api/v1/work-orders/{work_order['id']}/events").status_code == 401
    assert client.get('/api/v1/work-orders/999999/events').status_code == 404


def test_assignment_reassignment_unassignment_and_noop_dedup(client, seed):
    work_order = create_work_order(client, seed); work_order_id = work_order['id']
    payload = {'assigned_to':seed['admin'].id,'assigned_team':'Dock A'}
    assert client.post(f'/api/v1/work-orders/{work_order_id}/assign', json=payload).status_code == 200
    assert client.post(f'/api/v1/work-orders/{work_order_id}/assign', json=payload).status_code == 200
    assert client.post(f'/api/v1/work-orders/{work_order_id}/assign', json={'assigned_to':seed['viewer'].id,'assigned_team':'Dock B'}).status_code == 200
    assert client.post(f'/api/v1/work-orders/{work_order_id}/assign', json={'assigned_to':None,'assigned_team':None}).status_code == 200
    rows = events(client, work_order_id, order='asc')['data']
    assert [row['event_type'] for row in rows] == ['WORK_ORDER_CREATED','ASSIGNED','REASSIGNED','UNASSIGNED']
    assert rows[1]['field_name'] == 'assignment' and rows[1]['old_value'] is None
    assert 'Dock B' in rows[2]['new_value'] and rows[3]['new_value'] is None


def test_specific_and_generic_updates_pagination_and_noop(client, seed):
    work_order = create_work_order(client, seed); work_order_id = work_order['id']
    change = {'priority':'HIGH','notes':'Handle first','scheduled_at':'2026-08-31T09:30:00Z'}
    assert client.patch(f'/api/v1/work-orders/{work_order_id}', json=change).status_code == 200
    assert client.patch(f'/api/v1/work-orders/{work_order_id}', json=change).status_code == 200
    ascending = events(client, work_order_id, order='asc')['data']
    assert [row['event_type'] for row in ascending] == ['WORK_ORDER_CREATED','PRIORITY_CHANGED','NOTE_UPDATED','WORK_ORDER_UPDATED']
    assert [row['field_name'] for row in ascending[1:]] == ['priority','notes','scheduled_at']
    page = events(client, work_order_id, order='desc', limit=2, offset=1)
    assert page['total'] == 4 and len(page['data']) == 2
    assert [row['id'] for row in page['data']] == [ascending[2]['id'], ascending[1]['id']]
    assert client.get(f'/api/v1/work-orders/{work_order_id}/events', params={'order':'sideways'}).status_code == 422


def test_status_events_failed_operations_and_terminal_updates_emit_nothing(client, seed):
    work_order = create_work_order(client, seed); work_order_id = work_order['id']
    assert client.post(f'/api/v1/work-orders/{work_order_id}/status', json={'status':'ASSIGNED'}).status_code == 200
    before_failure = events(client, work_order_id)['total']
    assert client.post(f'/api/v1/work-orders/{work_order_id}/status', json={'status':'COMPLETED'}).status_code == 409
    assert events(client, work_order_id)['total'] == before_failure
    assert client.post(f'/api/v1/work-orders/{work_order_id}/status', json={'status':'IN_PROGRESS'}).status_code == 200
    assert client.post(f'/api/v1/work-orders/{work_order_id}/status', json={'status':'COMPLETED'}).status_code == 200
    completed_count = events(client, work_order_id)['total']
    assert client.patch(f'/api/v1/work-orders/{work_order_id}', json={'notes':'too late'}).status_code == 409
    rows = events(client, work_order_id, order='asc')['data']
    assert len(rows) == completed_count
    status_rows = [row for row in rows if row['event_type'] == 'STATUS_CHANGED']
    assert [(row['old_value'],row['new_value']) for row in status_rows] == [('OPEN','ASSIGNED'),('ASSIGNED','IN_PROGRESS'),('IN_PROGRESS','COMPLETED')]


def test_load_work_order_history_is_available_without_load_event_embedding(client, seed):
    load = client.post('/api/v1/loads', json={'warehouse_id':seed['warehouse'].id,'dispatch_business_type':'PRIVATE','outbound_ids':[]}).json()
    work_order = client.post('/api/v1/work-orders', json={'work_order_type':'LOAD','warehouse_id':seed['warehouse'].id,'load_id':load['id']}).json()
    detail = client.get(f"/api/v1/loads/{load['id']}").json()
    assert detail['work_orders'][0]['id'] == work_order['id']
    assert 'events' not in detail['work_orders'][0]
    assert events(client, work_order['id'])['data'][0]['event_type'] == 'WORK_ORDER_CREATED'
