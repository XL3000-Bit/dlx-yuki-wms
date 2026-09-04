from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuditLog,BOL,BOLStatus,FBAInventoryAllocation,InventoryLot,InventoryTransaction,OutboundInventoryAllocation,OutboundInventoryIdempotency,OutboundOrder,PickingList,PickingListItem,PickingStatus
from app.models.inventory import TransactionType
def inventory(client,seed,container='OB-CNTR',pallet=10):
 p={'container_number':container,'customer_id':seed['customer'].id,'warehouse_id':seed['warehouse'].id,'received_date':str(date.today()),'fc_code':'ONT8','pallet_qty':pallet,'carton_qty':20,'weight_lbs':1000,'cbm':5,'location_id':seed['location'].id,'status':3};i=client.post('/api/v1/inbound',json=p).json();return client.post(f"/api/v1/inbound/{i['id']}/receive-to-inventory").json()
def ob(seed):return {'customer_id':seed['customer'].id,'warehouse_id':seed['warehouse'].id,'carrier_id':seed['carrier'].id,'ob_type':'STANDARD','delivery_type':'FTL'}
def test_normal_outbound_lifecycle(client:TestClient,db:Session,seed):
 lot=inventory(client,seed);o=client.post('/api/v1/outbounds',json=ob(seed)).json();a=client.post(f"/api/v1/outbounds/{o['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':6});assert a.status_code==200,a.text;assert client.post(f"/api/v1/outbounds/{o['id']}/confirm").status_code==200
 picking=PickingList(picking_no='PICK-OUTBOUND-LIFECYCLE',outbound_order_id=o['id'],status=PickingStatus.COMPLETED,created_by=seed['admin'].id);db.add(picking);db.flush();db.add(PickingListItem(picking_list_id=picking.id,outbound_allocation_id=a.json()['id'],inventory_lot_id=lot['id'],location_id=seed['location'].id,lot_no=lot['lot_no'],container_number=lot['container_number'],planned_pallet_qty=6,picked_pallet_qty=6));db.add(BOL(bol_no='BOL-OUTBOUND-LIFECYCLE',outbound_order_id=o['id'],customer_id=seed['customer'].id,warehouse_id=seed['warehouse'].id,carrier_id=seed['carrier'].id,ship_from_name='DLX Test Warehouse',ship_from_address='1 Warehouse Way',status=BOLStatus.GENERATED,created_by=seed['admin'].id));db.commit()
 assert client.post(f"/api/v1/outbounds/{o['id']}/dispatch").status_code==200;done=client.post(f"/api/v1/outbounds/{o['id']}/complete");assert done.status_code==200,done.text;db.expire_all();x=db.get(InventoryLot,lot['id']);assert x.available_pallet_qty==4 and x.allocated_pallet_qty==0;assert client.post(f"/api/v1/outbounds/{o['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':1}).status_code==409
def test_overallocation_and_cancel_release(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,pallet=5);o=client.post('/api/v1/outbounds',json=ob(seed)).json();u=f"/api/v1/outbounds/{o['id']}/allocate";assert client.post(u,json={'inventory_lot_id':lot['id'],'pallet_qty':4}).status_code==200;assert client.post(u,json={'inventory_lot_id':lot['id'],'pallet_qty':3}).status_code==409;assert client.post(f"/api/v1/outbounds/{o['id']}/cancel").status_code==200;db.expire_all();assert db.get(InventoryLot,lot['id']).available_pallet_qty==5
def test_exception_and_fba_outbound_balance(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,pallet=10);f=client.post('/api/v1/fba',json={'warehouse_id':seed['warehouse'].id,'customer_id':seed['customer'].id,'amazon_fc_code':'ONT8'}).json();fa=client.post(f"/api/v1/fba/{f['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':10}).json();o=client.post('/api/v1/outbounds',json={**ob(seed),'ob_type':'FBA','fba_shipment_id':f['id'],'fc_code':'ONT8'}).json();a=client.post(f"/api/v1/outbounds/{o['id']}/allocate",json={'inventory_lot_id':lot['id'],'fba_allocation_id':fa['id'],'pallet_qty':6});assert a.status_code==200,a.text;db.expire_all();assert db.get(InventoryLot,lot['id']).allocated_pallet_qty==10;assert client.post(f"/api/v1/outbounds/{o['id']}/cancel").status_code==200;db.expire_all();assert db.get(InventoryLot,lot['id']).allocated_pallet_qty==10;assert db.get(FBAInventoryAllocation,fa['id']).allocated_pallet_qty==10
def test_workbench_sources_expose_current_quantities_for_batch_move(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,container='BATCH-MOVE',pallet=10);standard=client.post('/api/v1/outbounds',json=ob(seed)).json();standard_source=client.get(f"/api/v1/outbounds/{standard['id']}/workbench-detail").json()['remaining_sources'][0];assert standard_source['available_pallet_qty']=='10.00';assert standard_source['available_weight_lbs']=='1000.00';assert standard_source['available_cbm']=='5.0000'
 f=client.post('/api/v1/fba',json={'warehouse_id':seed['warehouse'].id,'customer_id':seed['customer'].id,'amazon_fc_code':'ONT8'}).json();fa=client.post(f"/api/v1/fba/{f['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':10,'carton_qty':20,'weight_lbs':1000,'cbm':5}).json();outbound=client.post('/api/v1/outbounds',json={**ob(seed),'ob_type':'FBA','fba_shipment_id':f['id'],'fc_code':'ONT8'}).json();allocated=client.post(f"/api/v1/outbounds/{outbound['id']}/allocate",json={'inventory_lot_id':lot['id'],'fba_allocation_id':fa['id'],'pallet_qty':6,'carton_qty':12,'weight_lbs':600,'cbm':3});assert allocated.status_code==200,allocated.text
 sources=client.get(f"/api/v1/outbounds/{outbound['id']}/workbench-detail").json()['remaining_sources'];assert len(sources)==1;source=sources[0];assert source['inventory_lot_id']==lot['id'];assert source['remaining_pallet_qty']=='4.00';assert source['remaining_carton_qty']=='8.00';assert source['remaining_weight_lbs']=='400.00';assert source['remaining_cbm']=='2.0000'
def test_batch_delete_only_removes_pristine_new_drafts(client:TestClient,db:Session,seed):
 clean=client.post('/api/v1/outbounds',json={**ob(seed),'reference_no':'DELETE-ME'}).json();blocked=client.post('/api/v1/outbounds',json={**ob(seed),'reference_no':'KEEP-ME'}).json();lot=inventory(client,seed,container='DELETE-BLOCKER');assert client.post(f"/api/v1/outbounds/{blocked['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':1}).status_code==200
 rows=client.get('/api/v1/outbounds/workbench',params={'per_page':100}).json()['data'];by_id={row['id']:row for row in rows};assert by_id[clean['id']]['allowed_actions']['delete'] is True;assert by_id[blocked['id']]['allowed_actions']['delete'] is False
 response=client.post('/api/v1/outbounds/workbench/batch',json={'action':'delete','ids':[clean['id'],blocked['id']]});assert response.status_code==200,response.text;result=response.json();assert result['successful']==1 and result['failed']==1;assert 'inventory allocation' in result['results'][1]['reason']
 db.expire_all();assert db.get(OutboundOrder,clean['id']) is None;assert db.get(OutboundOrder,blocked['id']) is not None;audit=db.scalar(select(AuditLog).where(AuditLog.action=='DELETE_OUTBOUND',AuditLog.entity_id==clean['id']));assert audit is not None;assert audit.before_data['ob_no']==clean['ob_no'] and audit.before_data['reference_no']=='DELETE-ME'
def batch_allocate_payload(lot_id:int,pallet_qty:int=3,item_id:int=101):
 return {'action':'allocate','items':[{'id':item_id,'data':{'inventory_lot_id':lot_id,'pallet_qty':pallet_qty}}]}

def test_inventory_batch_allocate_replay_has_exactly_once_side_effects(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,container='BATCH-ALLOCATE-REPLAY',pallet=10);outbound=client.post('/api/v1/outbounds',json=ob(seed)).json();url=f"/api/v1/outbounds/{outbound['id']}/inventory/batch";payload=batch_allocate_payload(lot['id'])
 first=client.post(url,json=payload,headers={'Idempotency-Key':'allocate-replay'});second=client.post(url,json=payload,headers={'Idempotency-Key':'allocate-replay'})
 assert first.status_code==200,first.text;assert second.status_code==200,second.text;assert first.json()==second.json();assert first.headers['Idempotency-Replayed']=='false';assert second.headers['Idempotency-Replayed']=='true'
 db.expire_all();stored=db.get(InventoryLot,lot['id']);assert stored.available_pallet_qty==7 and stored.allocated_pallet_qty==3
 assert len(db.scalars(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id==outbound['id'])).all())==1
 assert len(db.scalars(select(InventoryTransaction).where(InventoryTransaction.reference_type=='OUTBOUND',InventoryTransaction.reference_id==outbound['id'],InventoryTransaction.transaction_type==TransactionType.OUTBOUND_ALLOCATE)).all())==1
 assert len(db.scalars(select(AuditLog).where(AuditLog.entity_id==outbound['id'],AuditLog.action=='ALLOCATE_OUTBOUND_INVENTORY')).all())==1
 assert len(db.scalars(select(OutboundInventoryIdempotency).where(OutboundInventoryIdempotency.scope==f"warehouse:{seed['warehouse'].id}:outbound:{outbound['id']}")).all())==1

def test_inventory_batch_release_replay_has_exactly_once_side_effects(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,container='BATCH-RELEASE-REPLAY',pallet=10);outbound=client.post('/api/v1/outbounds',json=ob(seed)).json();allocation=client.post(f"/api/v1/outbounds/{outbound['id']}/allocate",json={'inventory_lot_id':lot['id'],'pallet_qty':6}).json();url=f"/api/v1/outbounds/{outbound['id']}/inventory/batch";payload={'action':'release','items':[{'id':allocation['id'],'data':{'allocation_id':allocation['id'],'pallet_qty':2}}]}
 first=client.post(url,json=payload,headers={'Idempotency-Key':'release-replay'});second=client.post(url,json=payload,headers={'Idempotency-Key':'release-replay'})
 assert first.status_code==200,first.text;assert second.status_code==200,second.text;assert first.json()==second.json();assert second.headers['Idempotency-Replayed']=='true'
 db.expire_all();stored=db.get(InventoryLot,lot['id']);assert stored.available_pallet_qty==6 and stored.allocated_pallet_qty==4
 assert len(db.scalars(select(InventoryTransaction).where(InventoryTransaction.reference_id==outbound['id'],InventoryTransaction.transaction_type==TransactionType.OUTBOUND_RELEASE)).all())==1
 assert len(db.scalars(select(AuditLog).where(AuditLog.entity_id==outbound['id'],AuditLog.action=='RELEASE_OUTBOUND_INVENTORY')).all())==1

def test_inventory_batch_rejects_reused_key_with_different_request(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,container='BATCH-CONFLICT',pallet=10);outbound=client.post('/api/v1/outbounds',json=ob(seed)).json();url=f"/api/v1/outbounds/{outbound['id']}/inventory/batch"
 assert client.post(url,json=batch_allocate_payload(lot['id'],2),headers={'Idempotency-Key':'same-key'}).status_code==200
 conflict=client.post(url,json=batch_allocate_payload(lot['id'],3),headers={'Idempotency-Key':'same-key'});assert conflict.status_code==409;assert conflict.json()['detail']['code']=='OUTBOUND_IDEMPOTENCY_CONFLICT'
 db.expire_all();stored=db.get(InventoryLot,lot['id']);assert stored.available_pallet_qty==8 and stored.allocated_pallet_qty==2

def test_inventory_batch_different_keys_execute_independently(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,container='BATCH-DIFFERENT-KEYS',pallet=10);outbound=client.post('/api/v1/outbounds',json=ob(seed)).json();url=f"/api/v1/outbounds/{outbound['id']}/inventory/batch";payload=batch_allocate_payload(lot['id'])
 assert client.post(url,json=payload,headers={'Idempotency-Key':'key-one'}).status_code==200;assert client.post(url,json=payload,headers={'Idempotency-Key':'key-two'}).status_code==200
 db.expire_all();stored=db.get(InventoryLot,lot['id']);assert stored.available_pallet_qty==4 and stored.allocated_pallet_qty==6
 assert len(db.scalars(select(InventoryTransaction).where(InventoryTransaction.reference_id==outbound['id'],InventoryTransaction.transaction_type==TransactionType.OUTBOUND_ALLOCATE)).all())==2
 assert len(db.scalars(select(AuditLog).where(AuditLog.entity_id==outbound['id'],AuditLog.action=='ALLOCATE_OUTBOUND_INVENTORY')).all())==2

def test_inventory_batch_requires_a_valid_idempotency_key(client:TestClient,seed):
 lot=inventory(client,seed,container='BATCH-KEY-VALIDATION',pallet=10);outbound=client.post('/api/v1/outbounds',json=ob(seed)).json();url=f"/api/v1/outbounds/{outbound['id']}/inventory/batch";payload=batch_allocate_payload(lot['id'])
 missing=client.post(url,json=payload);invalid=client.post(url,json=payload,headers={'Idempotency-Key':'contains whitespace'})
 assert missing.status_code==400 and missing.json()['detail']['code']=='OUTBOUND_IDEMPOTENCY_KEY_REQUIRED';assert invalid.status_code==400 and invalid.json()['detail']['code']=='OUTBOUND_IDEMPOTENCY_KEY_INVALID'

def test_inventory_batch_failure_rolls_back_all_writes_and_same_key_can_retry(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,container='BATCH-ATOMIC',pallet=5);outbound=client.post('/api/v1/outbounds',json=ob(seed)).json();url=f"/api/v1/outbounds/{outbound['id']}/inventory/batch";payload={'action':'allocate','items':[{'id':101,'data':{'inventory_lot_id':lot['id'],'pallet_qty':3}},{'id':102,'data':{'inventory_lot_id':lot['id'],'pallet_qty':9}}]}
 failed=client.post(url,json=payload,headers={'Idempotency-Key':'atomic-retry'});assert failed.status_code==409,failed.text;assert failed.json()['detail']['item_id']==102
 db.expire_all();stored=db.get(InventoryLot,lot['id']);assert stored.available_pallet_qty==5 and stored.allocated_pallet_qty==0
 assert db.scalar(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id==outbound['id'])) is None;assert db.scalar(select(OutboundInventoryIdempotency).where(OutboundInventoryIdempotency.idempotency_key=='atomic-retry')) is None
 assert db.scalar(select(InventoryTransaction).where(InventoryTransaction.reference_type=='OUTBOUND',InventoryTransaction.reference_id==outbound['id'],InventoryTransaction.transaction_type==TransactionType.OUTBOUND_ALLOCATE)) is None;assert db.scalar(select(AuditLog).where(AuditLog.entity_id==outbound['id'],AuditLog.action=='ALLOCATE_OUTBOUND_INVENTORY')) is None
 stored.original_pallet_qty=12;stored.available_pallet_qty=12;db.commit();retried=client.post(url,json=payload,headers={'Idempotency-Key':'atomic-retry'});assert retried.status_code==200,retried.text
 db.expire_all();stored=db.get(InventoryLot,lot['id']);assert stored.available_pallet_qty==0 and stored.allocated_pallet_qty==12

def test_inventory_batch_replay_works_in_a_new_database_session(client:TestClient,db:Session,seed):
 from app.api.deps import get_db
 from app.main import app
 lot=inventory(client,seed,container='BATCH-NEW-SESSION',pallet=10);outbound=client.post('/api/v1/outbounds',json=ob(seed)).json();url=f"/api/v1/outbounds/{outbound['id']}/inventory/batch";payload=batch_allocate_payload(lot['id'])
 first=client.post(url,json=payload,headers={'Idempotency-Key':'new-session'});assert first.status_code==200,first.text
 with Session(bind=db.get_bind()) as fresh_db:
  def override():yield fresh_db
  app.dependency_overrides[get_db]=override;second=client.post(url,json=payload,headers={'Idempotency-Key':'new-session'})
 assert second.status_code==200,second.text;assert second.headers['Idempotency-Replayed']=='true';assert second.json()==first.json()

def test_inventory_batch_key_scope_isolated_by_outbound(client:TestClient,db:Session,seed):
 lot=inventory(client,seed,container='BATCH-SCOPE',pallet=10);first_ob=client.post('/api/v1/outbounds',json=ob(seed)).json();second_ob=client.post('/api/v1/outbounds',json=ob(seed)).json();payload=batch_allocate_payload(lot['id'],2)
 for outbound in (first_ob,second_ob):
  response=client.post(f"/api/v1/outbounds/{outbound['id']}/inventory/batch",json=payload,headers={'Idempotency-Key':'shared-key'});assert response.status_code==200,response.text
 db.expire_all();stored=db.get(InventoryLot,lot['id']);assert stored.available_pallet_qty==6 and stored.allocated_pallet_qty==4
