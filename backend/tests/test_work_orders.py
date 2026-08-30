from fastapi.testclient import TestClient
from app.main import app
from app.models import Load, OutboundOrder, PickingList
from app.services.load import generate_load_no

def refs(db,seed):
    ob=OutboundOrder(ob_no='WO-OB-1',warehouse_id=seed['warehouse'].id,customer_id=seed['customer'].id,created_by=seed['admin'].id,status=0,po_number=None);db.add(ob);db.flush();pick=PickingList(picking_no='WO-PICK-1',outbound_order_id=ob.id,status=0,created_by=seed['admin'].id);db.add(pick);db.commit();return ob,pick
def test_create_types_priority_and_picking_link(client,db,seed):
    ob,pick=refs(db,seed);r=client.post('/api/v1/work-orders',json={'work_order_type':'PICK','warehouse_id':seed['warehouse'].id,'outbound_id':ob.id,'picking_list_id':pick.id,'priority':'URGENT'});assert r.status_code==201;assert r.json()['work_order_no'].startswith('WO-') and r.json()['priority']=='URGENT'
def test_status_assignment_terminal_and_auth(client,db,seed):
    r=client.post('/api/v1/work-orders',json={'work_order_type':'GENERAL','warehouse_id':seed['warehouse'].id,'assigned_to':seed['admin'].id});assert r.status_code==201;wo=r.json();assert client.post(f"/api/v1/work-orders/{wo['id']}/status",json={'status':'ASSIGNED'}).status_code==200;assert client.post(f"/api/v1/work-orders/{wo['id']}/status",json={'status':'COMPLETED'}).status_code==409;assert client.post(f"/api/v1/work-orders/{wo['id']}/status",json={'status':'IN_PROGRESS'}).status_code==200;assert client.post(f"/api/v1/work-orders/{wo['id']}/status",json={'status':'COMPLETED'}).status_code==200;assert client.post(f"/api/v1/work-orders/{wo['id']}/status",json={'status':'CANCELED'}).status_code==409;assert TestClient(app).get('/api/v1/work-orders').status_code==401
def test_invalid_related_and_filters(client,db,seed):
    assert client.post('/api/v1/work-orders',json={'work_order_type':'NOPE','warehouse_id':seed['warehouse'].id}).status_code==422;assert client.get('/api/v1/work-orders',params={'status':'OPEN','work_order_type':'PICK','priority':'HIGH'}).status_code==200
