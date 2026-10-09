from fastapi.testclient import TestClient
from app.main import app
from app.models import Load, OutboundOrder
from app.models.load import LoadStatus

def make_obs(db, seed, count=2, warehouse=None):
    warehouse = warehouse or seed['warehouse']
    rows=[]
    start = db.query(OutboundOrder).count()
    for i in range(count):
        row=OutboundOrder(ob_no=f'LOAD-OB-{start+i}', warehouse_id=warehouse.id, customer_id=seed['customer'].id, created_by=seed['admin'].id, status=0, po_number=None, dispatch_business_type="PRIVATE")
        db.add(row); rows.append(row)
    db.commit(); return rows

def test_create_load_one_and_detail(client, db, seed):
    ob=make_obs(db,seed,1)[0]; response=client.post('/api/v1/loads',json={'dispatch_business_type':'PRIVATE','warehouse_id':seed['warehouse'].id,'outbound_ids':[ob.id]})
    assert response.status_code==201; data=response.json(); assert data['load_no'].startswith('LD-'); assert data['outbound_count']==1
    assert client.get(f"/api/v1/loads/{data['id']}").json()['outbounds'][0]['ob_no']==ob.ob_no

def test_multiple_and_duplicate_assignment_rejected(client, db, seed):
    one,two=make_obs(db,seed,2); created=client.post('/api/v1/loads',json={'dispatch_business_type':'PRIVATE','warehouse_id':seed['warehouse'].id,'outbound_ids':[one.id,two.id]}); assert created.status_code==201
    other=make_obs(db,seed,1)[0]; conflict=client.post('/api/v1/loads',json={'dispatch_business_type':'PRIVATE','warehouse_id':seed['warehouse'].id,'outbound_ids':[one.id,other.id]}); assert conflict.status_code==409

def test_cross_warehouse_rejected(client, db, seed):
    from app.models import Warehouse
    second=Warehouse(warehouse_code='SECOND',warehouse_name='Second',address='x',city='x',state='CA',zip_code='1');db.add(second);db.commit(); ob=make_obs(db,seed,1,second)[0]
    assert client.post('/api/v1/loads',json={'dispatch_business_type':'PRIVATE','warehouse_id':seed['warehouse'].id,'outbound_ids':[ob.id]}).status_code==409

def test_remove_totals_list_status_and_auth(client, db, seed):
    one,two=make_obs(db,seed,2); load=client.post('/api/v1/loads',json={'dispatch_business_type':'PRIVATE','warehouse_id':seed['warehouse'].id,'outbound_ids':[one.id,two.id]}).json(); assert client.delete(f"/api/v1/loads/{load['id']}/outbounds/{one.id}").status_code==200
    assert client.get('/api/v1/loads').json()['meta']['total']==1
    assert client.post(f"/api/v1/loads/{load['id']}/status",json={'status':'READY'}).status_code==200
    assert client.post(f"/api/v1/loads/{load['id']}/status",json={'status':'COMPLETED'}).status_code==409
    assert TestClient(app).get('/api/v1/loads').status_code==401

def test_load_number_unique_and_global_search(client, db, seed):
    ob=make_obs(db,seed,1)[0]; load=client.post('/api/v1/loads',json={'dispatch_business_type':'PRIVATE','warehouse_id':seed['warehouse'].id,'outbound_ids':[ob.id]}).json(); found=client.get('/api/v1/search',params={'q':load['load_no']}).json(); assert found['groups'][0]['type']=='LOAD'; assert found['groups'][0]['items'][0]['target_route'].startswith('/loads?selected=')
