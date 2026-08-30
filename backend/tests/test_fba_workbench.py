from datetime import date,timedelta
from app.core.security import create_access_token,hash_password
from app.models import User
from app.models.user import UserRole
from app.services.fba_workbench import resolve_workbench_stage
from tests.test_fba import fba_payload,make_lot

def create_allocated(client,seed,days,pallet,container):
    lot=make_lot(client,seed,container=container,pallet=pallet,days=days);fba=client.post('/api/v1/fba',json={**fba_payload(seed),'shipment_id':f'SHIP-{days}','st_number':f'ST-{days}'}).json();response=client.post(f"/api/v1/fba/{fba['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':pallet,'carton_qty':10,'weight_lbs':pallet*100,'cbm':pallet});assert response.status_code==200,response.text;return fba,response.json()

def test_workbench_priority_pagination_summary_and_search(client,seed):
    a,_=create_allocated(client,seed,25,6,'OLD-25');b,_=create_allocated(client,seed,10,8,'MID-10');c,_=create_allocated(client,seed,3,4,'NEW-03')
    body=client.get('/api/v1/fba/workbench',params={'per_page':2}).json();assert [x['id']for x in body['data']]==[a['id'],b['id']],[(x['id'],x['max_aging_days'],x['priority_rank'])for x in body['data']];assert body['summary']['total_pallet_qty']=='18.00';assert body['meta']['total']==3;assert body['stage_counts']['waiting_picking']==3
    found=client.get('/api/v1/fba/workbench',params={'q':'MID-10'}).json();assert found['meta']['total']==1;assert found['data'][0]['id']==b['id']
    detail=client.get(f"/api/v1/fba/{c['id']}/workbench-detail");assert detail.status_code==200;assert detail.json()['inventory_sources'][0]['container_number']=='NEW-03'

def test_stage_resolver_critical_order():
    assert resolve_workbench_stage(fba_status=2,outbound_status=3,picking_status=0,has_picking=True,appointment_time=None,remaining=6)=='waiting_appointment'
    assert resolve_workbench_stage(fba_status=2,outbound_status=3,picking_status=3,has_picking=True,appointment_time=date.today(),remaining=6)=='waiting_outbound'
    assert resolve_workbench_stage(fba_status=2,outbound_status=5,picking_status=3,has_picking=True,appointment_time=date.today(),remaining=0)=='completed'
    assert resolve_workbench_stage(fba_status=8,outbound_status=None,picking_status=None,has_picking=False,appointment_time=None,remaining=1)=='exception'

def test_outbound_permission_and_viewer_read(client,db,seed):
    outbound=User(username='ob-user',display_name='OB',email='ob@test.local',password_hash=hash_password('Password123!'),role=UserRole.OUTBOUND);inbound=User(username='in-user',display_name='IN',email='in@test.local',password_hash=hash_password('Password123!'),role=UserRole.INBOUND);db.add_all([outbound,inbound]);db.commit()
    client.headers['Authorization']=f"Bearer {create_access_token(str(outbound.id))}";assert client.post('/api/v1/fba',json=fba_payload(seed)).status_code==201
    client.headers['Authorization']=f"Bearer {create_access_token(str(inbound.id))}";assert client.post('/api/v1/fba',json=fba_payload(seed)).status_code==403;assert client.get('/api/v1/fba/workbench').status_code==200

def test_batch_outbound_and_idempotency(client,seed):
    fba,_=create_allocated(client,seed,4,2,'BATCH-1')
    first=client.post('/api/v1/fba/workbench/batch',json={'action':'outbound','fba_ids':[fba['id']]});assert first.status_code==200,first.text;assert first.json()['successful']==1
    second=client.post('/api/v1/fba/workbench/batch',json={'action':'outbound','fba_ids':[fba['id']]});assert second.status_code==200;assert second.json()['skipped']==1

def test_selected_export_and_batch_missing_fc_bol(client,seed):
    fba,_=create_allocated(client,seed,2,1,'EXPORT-1');export=client.post('/api/v1/fba/workbench/export-selected',json={'fba_ids':[fba['id']]});assert export.status_code==200;assert export.headers['content-type'].startswith('application/vnd.openxmlformats');assert len(export.content)>100
    assert client.post('/api/v1/fba/workbench/batch',json={'action':'bol','fba_ids':[fba['id']]}).json()['skipped']==1
