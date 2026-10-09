from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.models import Customer,InventoryLot,OutboundInventoryAllocation,OutboundOrder
def make_lot(client,seed,container,pallet=5):
 p={'container_number':container,'customer_id':seed['customer'].id,'warehouse_id':seed['warehouse'].id,'received_date':str(date.today()),'fc_code':'ONT8','pallet_qty':pallet,'carton_qty':5,'weight_lbs':100,'cbm':1,'location_id':seed['location'].id,'status':3};i=client.post('/api/v1/inbound',json=p).json();return client.post(f"/api/v1/inbound/{i['id']}/receive-to-inventory").json()
def test_outbound_import_preview_alias_group_and_confirm(client:TestClient,db:Session,seed):
 a=make_lot(client,seed,'IMP-OB-A');b=make_lot(client,seed,'IMP-OB-B');csv=f"OB#,OB Type,Warehouse,Container Number,FC,Pallet Qty\nOB-IMPORT,STANDARD,DLX-LAX,IMP-OB-A,ONT8,2\nOB-IMPORT,STANDARD,DLX-LAX,IMP-OB-B,ONT8,3\n".encode();p=client.post('/api/v1/imports/outbound/preview',files={'file':('outbound.csv',csv,'text/csv')});assert p.status_code==201,p.text;body=p.json();assert body['suggested_mapping']['OB#']=='ob_no';v=client.post(f"/api/v1/imports/outbound/{body['job_id']}/validate",json={'mapping':body['suggested_mapping']});assert v.status_code==200,v.text;assert v.json()['valid_rows']==2;r=client.post(f"/api/v1/imports/outbound/{body['job_id']}/confirm",json={'mapping':body['suggested_mapping']});assert r.status_code==200,r.text;assert r.json()['imported_rows']==2;assert db.scalar(select(func.count()).select_from(OutboundOrder))==1;assert db.scalar(select(func.count()).select_from(OutboundInventoryAllocation))==2
def test_outbound_import_cumulative_overallocation(client:TestClient,seed):
 make_lot(client,seed,'IMP-OB-LIMIT',5);csv=b"OB#,Warehouse,Container Number,FC,Pallet Qty\nOB1,DLX-LAX,IMP-OB-LIMIT,ONT8,3\nOB2,DLX-LAX,IMP-OB-LIMIT,ONT8,3\n";p=client.post('/api/v1/imports/outbound/preview',files={'file':('over.csv',csv)}).json();v=client.post(f"/api/v1/imports/outbound/{p['job_id']}/validate",json={'mapping':p['suggested_mapping']}).json();assert v['error_rows']==1;assert any(x['code']=='OVER_ALLOCATION' for row in v['rows'] for x in row['issues'])

def test_outbound_import_preserves_inventory_customer(client:TestClient,db:Session,seed):
    make_lot(client,seed,'IMPORT-OWNER')
    db.add(Customer(customer_code='OTHER',customer_name='Other Customer'));db.commit()
    for customer,expected in [('',None),('ACME',None),('OTHER','CUSTOMER_MISMATCH'),('MISSING','UNKNOWN_CUSTOMER')]:
        csv=f'OB#,Warehouse,Container Number,FC,Pallet Qty,Customer\nOWNER-{customer or "DEFAULT"},DLX-LAX,IMPORT-OWNER,ONT8,1,{customer}\n'.encode()
        preview=client.post('/api/v1/imports/outbound/preview',files={'file':('owner.csv',csv)})
        assert preview.status_code==201,preview.text
        body=preview.json();mapping={'mapping':body['suggested_mapping']}
        validation=client.post(f'/api/v1/imports/outbound/{body["job_id"]}/validate',json=mapping)
        assert validation.status_code==200,validation.text
        data=validation.json()
        if expected:
            assert data['error_rows']==1
            assert any(issue['code']==expected for row in data['rows'] for issue in row['issues'])
        else:
            assert data['valid_rows']==1
            assert data['rows'][0]['data']['customer_id']==seed['customer'].id
            confirmed=client.post(f'/api/v1/imports/outbound/{body["job_id"]}/confirm',json=mapping)
            assert confirmed.status_code==200,confirmed.text
    orders=db.scalars(select(OutboundOrder)).all()
    assert len(orders)==2
    assert all(order.customer_id==seed['customer'].id for order in orders)
