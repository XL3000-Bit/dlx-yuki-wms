"""Synthetic migration safety regressions; run with isolated PostgreSQL fixtures."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models import InboundRecord, InventoryLot, PickingList
from app.services.phase8_import import validate_profile_job, confirm_profile_job
from app.services.import_safety import rollback_batch
from test_phase8_import import make_book, stage
from test_outbound import inventory, ob
from tests.dispatch_history import mark_historical_dispatched

def batch(tmp_path, db, seed, name, rows=None):
    headers=['来源记录ID','业务单号','明细ID','客户','柜号','仓点','板数','件数','备注','预期版本','导入用途']
    rows=rows or [['SRC1','DOC1','LINE1','ACME','SYNTHETIC','ONT8',10,20,'original',None,'HISTORICAL']]
    path=make_book(tmp_path/name,'OL',headers,rows)
    job,_=stage(db,seed,path,'WEST_COAST_4_0_OL','OL')
    result=validate_profile_job(db,job)
    assert result.error_rows==0, result
    return job

def confirm(db,job,seed,**kw):
    return confirm_profile_job(db,job,seed['admin'].id,**kw)

def test_same_and_cross_file_duplicate_and_legal_details(tmp_path,db,seed):
    a=batch(tmp_path,db,seed,'a.xlsx');confirm(db,a,seed)
    b=batch(tmp_path,db,seed,'a.xlsx');assert confirm(db,b,seed).skipped_rows==1
    c=batch(tmp_path,db,seed,'c.xlsx');assert confirm(db,c,seed).skipped_rows==1
    d=batch(tmp_path,db,seed,'details.xlsx',[
        ['SRC2','DOC1','LINE2','ACME','SYNTHETIC','ONT8',2,4,'',None,'HISTORICAL'],
        ['SRC3','DOC1','LINE3','ACME','SYNTHETIC','ONT8',3,6,'',None,'HISTORICAL']])
    assert confirm(db,d,seed).imported_rows==2
    assert db.query(InboundRecord).count()==3
    assert db.query(InventoryLot).count()==0

def test_revision_conflict_update_and_reverse_update(tmp_path,db,seed):
    a=batch(tmp_path,db,seed,'a.xlsx');confirm(db,a,seed)
    changed=[['SRC1','DOC1','LINE1','ACME','SYNTHETIC','ONT8',9,18,'revised',1,'HISTORICAL']]
    b=batch(tmp_path,db,seed,'b.xlsx',changed)
    with pytest.raises(HTTPException,match='SOURCE_CHANGED'):confirm(db,b,seed)
    c=batch(tmp_path,db,seed,'c.xlsx',changed);confirm(db,c,seed,duplicate_strategy='UPDATE')
    assert db.query(InboundRecord).one().pallet_qty==9
    assert c.options['migration_journal']['changes']
    with pytest.raises(HTTPException):rollback_batch(db,a.id,seed['admin'])
    db.rollback()
    rollback_batch(db,c.id,seed['admin'])
    assert db.query(InboundRecord).one().pallet_qty==10

def test_business_collision_rejected_atomically(tmp_path,db,seed):
    a=batch(tmp_path,db,seed,'a.xlsx');confirm(db,a,seed)
    b=batch(tmp_path,db,seed,'b.xlsx', [['SRC2','DOC1','LINE1','ACME','SYNTHETIC','ONT8',10,20,'',None,'HISTORICAL']])
    with pytest.raises(HTTPException,match='BUSINESS_KEY_CONFLICT'):confirm(db,b,seed)
    assert db.query(InboundRecord).count()==1

def test_history_no_stock_and_safe_rollback(tmp_path,db,seed,client):
    a=batch(tmp_path,db,seed,'a.xlsx')
    with pytest.raises(HTTPException,match='HISTORICAL_STOCK_BLOCKED'):confirm(db,a,seed,auto_receive_to_inventory=True)
    confirm(db,a,seed)
    item=db.query(InboundRecord).one()
    response=client.post(f'/api/v1/inbound/{item.id}/receive-to-inventory')
    assert response.status_code==409,response.text
    assert db.query(InventoryLot).count()==0
    result=rollback_batch(db,a.id,seed['admin'])
    assert result['status']=='ROLLED_BACK' and db.query(InboundRecord).count()==0

def test_downstream_change_blocks_rollback(tmp_path,db,seed):
    a=batch(tmp_path,db,seed,'a.xlsx');confirm(db,a,seed)
    item=db.query(InboundRecord).one();item.remark='subsequent operator change';db.commit()
    with pytest.raises(HTTPException) as exc:rollback_batch(db,a.id,seed['admin'])
    assert exc.value.detail['code']=='ROLLBACK_DEPENDENCY'
    db.rollback();assert db.query(InboundRecord).count()==1

def dispatched(client,db,seed):
    lot=inventory(client,seed,container='REGRESSION')
    order=client.post('/api/v1/outbounds',json=ob(seed)).json();url=f"/api/v1/outbounds/{order['id']}"
    response=client.post(url+'/allocate',json=dict(inventory_lot_id=lot['id'],pallet_qty=10,carton_qty=20,weight_lbs=1000,cbm=5))
    assert response.status_code==200,response.text
    allocation=response.json()
    assert client.post(url+'/confirm').status_code==200
    picking=db.scalar(select(PickingList).where(PickingList.outbound_order_id==order['id']))
    assert client.post(f'/api/v1/picking-lists/{picking.id}/complete',json={}).status_code==200
    response=client.post(url+'/dispatch');assert response.status_code==409,response.text
    mark_historical_dispatched(db,order['id'])
    return lot,order,url,allocation

def completion_state(db):
    from app.models import OutboundOrder, OutboundInventoryAllocation, FBAInventoryAllocation, InventoryTransaction, AuditLog
    db.expire_all()
    return {
        model.__tablename__: [dict(row) for row in db.execute(
            select(model.__table__).order_by(model.__table__.c.id)).mappings()]
        for model in (OutboundOrder, OutboundInventoryAllocation, InventoryLot,
                      FBAInventoryAllocation, InventoryTransaction, AuditLog, PickingList)
    }


@pytest.mark.parametrize('state', ['draft', 'confirmed'])
def test_draft_and_confirmed_partial_are_blocked(client,db,seed,state):
    lot=inventory(client,seed,container='DRAFT-REGRESSION')
    order=client.post('/api/v1/outbounds',json=ob(seed)).json();url=f"/api/v1/outbounds/{order['id']}"
    a=client.post(url+'/allocate',json=dict(inventory_lot_id=lot['id'],pallet_qty=10)).json()
    if state=='confirmed': assert client.post(url+'/confirm').status_code==200
    before=completion_state(db)
    response=client.post(url+'/complete',json=dict(allocation_id=a['id'],pallet_qty=1,request_id=state))
    assert response.status_code==409,response.text
    status_label={'draft':'New','confirmed':'Confirmed'}[state]
    assert response.json()['detail']==f'Invalid status transition: {status_label} to Completed'
    assert completion_state(db)==before
    db.expire_all();assert db.get(InventoryLot,lot['id']).allocated_pallet_qty==10

def test_partial_retry_overdraw_then_full(client,db,seed):
    lot,order,url,a=dispatched(client,db,seed)
    payload=dict(allocation_id=a['id'],pallet_qty=6,carton_qty=12,weight_lbs=600,cbm=3,request_id='ONCE')
    response=client.post(url+'/complete',json=payload);assert response.status_code==200,response.text
    before=completion_state(db)
    assert client.post(url+'/complete',json=payload).status_code==409
    assert completion_state(db)==before
    response=client.post(url+'/complete',json={**payload,'request_id':'TOO-MUCH'})
    assert response.status_code==409,response.text
    assert completion_state(db)==before
    db.expire_all();item=db.get(InventoryLot,lot['id'])
    assert tuple(getattr(item,'allocated_'+k) for k in ['pallet_qty','carton_qty','weight_lbs','cbm'])==(4,8,400,2)
    response=client.post(url+'/complete');assert response.status_code==200,response.text
    before=completion_state(db)
    assert client.post(url+'/complete').status_code==409
    assert completion_state(db)==before
    db.expire_all();item=db.get(InventoryLot,lot['id'])
    assert all(getattr(item,p+k)==0 for p in ['available_','allocated_'] for k in ['pallet_qty','carton_qty','weight_lbs','cbm'])

def test_concurrent_partial_cannot_overdraw(client,db,seed):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import sessionmaker
    from app.models import OutboundOrder
    from app.schemas.outbound import CompleteRequest
    from app.services.outbound import complete_partial
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('Requires real PostgreSQL row locks')
    lot,order,url,a=dispatched(client,db,seed)
    factory=sessionmaker(bind=db.bind); barrier=Barrier(2); user_id=seed['admin'].id
    def attempt(number):
        with factory() as session:
            target=session.get(OutboundOrder,order['id'])
            barrier.wait(timeout=10)
            try:
                complete_partial(session,target,user_id,CompleteRequest(allocation_id=a['id'],pallet_qty=7,
                    carton_qty=14,weight_lbs=700,cbm=3.5,request_id=f'CONCURRENT-{number}'))
                session.commit();return (number,200)
            except HTTPException as error:
                session.rollback();return (number,error.status_code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,[1,2]))
    assert sorted(status for _,status in results)==[200,409]
    db.expire_all();item=db.get(InventoryLot,lot['id'])
    assert tuple(getattr(item,'allocated_'+k) for k in ['pallet_qty','carton_qty','weight_lbs','cbm'])==(3,6,300,1.5)
    winner=next(number for number,status in results if status==200)
    before=completion_state(db)
    response=client.post(url+'/complete',json=dict(allocation_id=a['id'],pallet_qty=7,
        carton_qty=14,weight_lbs=700,cbm=3.5,request_id=f'CONCURRENT-{winner}'))
    assert response.status_code==409,response.text
    assert completion_state(db)==before

def test_new_receipt_stock_blocks_batch_rollback(tmp_path,db,seed,client):
    a=batch(tmp_path,db,seed,'new.xlsx', [['NEW1','NEW-DOC','LINE1','ACME','NEW-RECEIPT','ONT8',10,20,'',None,'NEW_RECEIPT']])
    confirm(db,a,seed)
    item=db.query(InboundRecord).one()
    # Simulate warehouse completion of unload/put-away before actual receipt.
    item.status=3;db.commit()
    response=client.post(f'/api/v1/inbound/{item.id}/receive-to-inventory')
    assert response.status_code==200,response.text
    assert db.query(InventoryLot).count()==1
    with pytest.raises(HTTPException) as exc:rollback_batch(db,a.id,seed['admin'])
    assert exc.value.detail['code']=='ROLLBACK_DEPENDENCY'
    db.rollback();assert db.query(InventoryLot).count()==1

def test_unknown_opening_balance_is_not_accepted(tmp_path,db,seed):
    path=make_book(tmp_path/'opening.xlsx','OL',['来源记录ID','业务单号','明细ID','客户','柜号','仓点','导入用途'],[['OPEN1','DOC1','L1','ACME','OPEN','ONT8','OPENING_BALANCE']])
    job,_=stage(db,seed,path,'WEST_COAST_4_0_OL','OL')
    result=validate_profile_job(db,job)
    assert result.error_rows==1
    assert any(x['code']=='BALANCE_RECONCILIATION_REQUIRED' for x in result.rows[0]['issues'])
    assert db.query(InventoryLot).count()==0


def test_legacy_import_without_identity_blocks_new_batch(tmp_path,db,seed):
    from app.models import ImportRow
    a=batch(tmp_path,db,seed,'legacy.xlsx');confirm(db,a,seed)
    row=db.query(ImportRow).filter_by(import_job_id=a.id).one()
    row.mapped_data={k:v for k,v in row.mapped_data.items() if k!='_identity'};db.commit()
    b=batch(tmp_path,db,seed,'new-copy.xlsx')
    with pytest.raises(HTTPException) as exc:confirm(db,b,seed)
    assert exc.value.detail['code']=='LEGACY_IDENTITY_RECONCILIATION_REQUIRED'
    db.rollback();assert db.query(InboundRecord).count()==1


@pytest.fixture
def uni_confirmed_partial(client,db,seed):
    from app.models import FBAShipment, UniBol, OutboundOrder
    from app.schemas.fba import AllocateRequest
    from app.services import fba
    def setup(missing_carrier=False,confirmed=True):
        lot=inventory(client,seed,container='UNI-CONFIRMED')
        shipment=FBAShipment(fba_no='UNI-PARAM-TEST',warehouse_id=seed['warehouse'].id,customer_id=seed['customer'].id,amazon_fc_code='ONT8',created_by=seed['admin'].id)
        db.add(shipment);db.flush()
        allocation=fba.allocate(db,shipment.id,AllocateRequest(inventory_lot_id=lot['id'],pallet_qty=10,carton_qty=20,weight_lbs=1000,cbm=5),seed['admin'].id,commit=False)
        order=client.post('/api/v1/outbounds',json={**ob(seed),'ob_type':'FBA','fba_shipment_id':shipment.id,'fc_code':'ONT8'}).json();url=f"/api/v1/outbounds/{order['id']}"
        assert client.post(url+'/allocate',json=dict(inventory_lot_id=lot['id'],fba_allocation_id=allocation.id,pallet_qty=10,carton_qty=20,weight_lbs=1000,cbm=5)).status_code==200
        if confirmed:
            assert client.post(url+'/confirm').status_code==200
        if missing_carrier:
            db.get(OutboundOrder,order['id']).carrier_id=None
            db.flush()
        record=UniBol(fba_shipment_id=shipment.id,outbound_order_id=order['id'],status='Confirmed' if confirmed else 'Pre',version=1)
        db.add(record)
        db.commit()
        return record,order['id'],lot['id']
    return setup


def uni_partial_payload(**changes):
    from app.schemas.uni_bol import BolAction
    values=dict(version=1,action='shipout',confirm_all_picked=True,request_id='UNI-INTERNAL-READY',lines=[])
    values.update(changes)
    return BolAction(**values)


def test_uni_shipout_cannot_bypass_load_gate(client,db,seed,uni_confirmed_partial):
    from app.services.uni_bol import action
    record,order_id,lot_id=uni_confirmed_partial()
    before=uni_transaction_snapshot(db)
    with pytest.raises(HTTPException) as error:
        action(db,seed['admin'],record.id,uni_partial_payload(lines=[dict(inventory_lot_id=lot_id,pallet_qty=1,carton_qty=2,weight_lbs=100,cbm=.5)]))
    assert error.value.status_code==409
    assert 'dispatch' in str(error.value.detail).lower()
    assert uni_transaction_snapshot(db)==before


@pytest.mark.parametrize('failure,expected', [('picking',422),('carrier',409)])
def test_uni_partial_preserves_own_guards(client,db,seed,uni_confirmed_partial,failure,expected):
    from app.services.uni_bol import action
    record,order_id,lot_id=uni_confirmed_partial(missing_carrier=failure=='carrier')
    before=completion_state(db)
    with pytest.raises(HTTPException) as error:
        action(db,seed['admin'],record.id,uni_partial_payload(confirm_all_picked=failure!='picking',lines=[dict(inventory_lot_id=lot_id,pallet_qty=1,carton_qty=2,weight_lbs=100,cbm=.5)]))
    assert error.value.status_code==expected
    assert completion_state(db)==before
    db.refresh(record)
    assert record.status=='Confirmed'
    assert record.version==1


def uni_transaction_snapshot(db):
    from copy import deepcopy
    from app.db.base import Base
    return deepcopy({table.name: [tuple(row) for row in db.execute(select(table).order_by(*table.primary_key.columns)).all()] for table in Base.metadata.sorted_tables})


@pytest.mark.parametrize('operation,expected_status,expected_ob', [('confirm', 'Confirmed', 3), ('cancel', 'Canceled', 6)])
def test_uni_action_transaction_commits_once(db, seed, uni_confirmed_partial, monkeypatch, operation, expected_status, expected_ob):
    from sqlalchemy import event
    from conftest import TestingSession
    import app.db.session as session_module
    from app.models import User, UniBol, OutboundOrder
    from app.services import uni_bol
    record, order_id, lot_id = uni_confirmed_partial(confirmed=operation != 'confirm')
    record_id, user_id = record.id, seed['admin'].id
    db.rollback()
    monkeypatch.setattr(session_module, 'SessionLocal', TestingSession)
    scope = session_module.get_db()
    tx = next(scope)
    commits = []
    event.listen(tx, 'after_commit', lambda session: commits.append(True))
    lines = [dict(inventory_lot_id=lot_id, pallet_qty=10, carton_qty=20, weight_lbs=1000, cbm=5)] if operation == 'shipout' else []
    try:
        uni_bol.action(tx, tx.get(User, user_id), record_id, uni_partial_payload(action=operation, lines=lines))
    finally:
        scope.close()
    assert commits == [True]
    with TestingSession() as verify:
        saved = verify.get(UniBol, record_id)
        assert saved.status == expected_status
        assert saved.version == 2
        assert verify.get(OutboundOrder, order_id).status == expected_ob
        if operation == 'cancel':
            from app.models import InventoryLot, FBAInventoryAllocation, OutboundInventoryAllocation, InventoryTransaction
            lot = verify.get(InventoryLot, lot_id)
            units = ('pallet_qty', 'carton_qty', 'weight_lbs', 'cbm')
            assert tuple(getattr(lot, 'original_' + unit) for unit in units) == (10, 20, 1000, 5)
            assert tuple(getattr(lot, 'available_' + unit) for unit in units) == (10, 20, 1000, 5)
            assert tuple(getattr(lot, 'allocated_' + unit) for unit in units) == (0, 0, 0, 0)
            fba_allocation = verify.scalar(select(FBAInventoryAllocation).where(FBAInventoryAllocation.fba_shipment_id == saved.fba_shipment_id))
            ob_allocation = verify.scalar(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id == order_id))
            assert ob_allocation.fba_allocation_id == fba_allocation.id
            for allocation in (fba_allocation, ob_allocation):
                assert tuple(getattr(allocation, 'allocated_' + unit) for unit in units) == (0, 0, 0, 0)
            transaction_types = list(verify.scalars(select(InventoryTransaction.transaction_type).where(InventoryTransaction.inventory_lot_id == lot_id)))
            assert transaction_types.count('FBA_RELEASE') == 1
            assert 'OUTBOUND_RELEASE' not in transaction_types
            assert 'OUTBOUND_COMPLETE' not in transaction_types


@pytest.mark.parametrize('operation', ['confirm', 'cancel'])
def test_uni_action_failure_rolls_back_all(db, seed, uni_confirmed_partial, monkeypatch, operation):
    from sqlalchemy import event
    from conftest import TestingSession
    import app.db.session as session_module
    from app.models import User
    from app.services import uni_bol
    record, order_id, lot_id = uni_confirmed_partial(confirmed=operation != 'confirm')
    record_id, user_id = record.id, seed['admin'].id
    before = uni_transaction_snapshot(db)
    db.rollback()
    monkeypatch.setattr(session_module, 'SessionLocal', TestingSession)
    injected = []
    def fail_before_commit(session, *args, **kwargs):
        session.flush()
        assert uni_transaction_snapshot(session) != before
        injected.append(True)
        raise RuntimeError('injected before UNI commit')
    monkeypatch.setattr(uni_bol, 'audit', fail_before_commit)
    scope = session_module.get_db()
    tx = next(scope)
    commits = []
    event.listen(tx, 'after_commit', lambda session: commits.append(True))
    lines = [dict(inventory_lot_id=lot_id, pallet_qty=10, carton_qty=20, weight_lbs=1000, cbm=5)] if operation == 'shipout' else []
    try:
        with pytest.raises(RuntimeError, match='injected before UNI commit'):
            uni_bol.action(tx, tx.get(User, user_id), record_id, uni_partial_payload(action=operation, lines=lines))
    finally:
        scope.close()
    assert commits == []
    assert injected == [True]
    with TestingSession() as verify:
        assert uni_transaction_snapshot(verify) == before
