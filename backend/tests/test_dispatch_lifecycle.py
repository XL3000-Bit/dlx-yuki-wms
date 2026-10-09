"""SQLite isolation: real writers/execution; synthetic policy approval only in marked tests."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.models import InboundRecord, InventoryLot, OutboundOrder, Load, PickingList, PickingListItem
from app.models.load import LoadStatus
from app.models.outbound import OutboundInventoryAllocation, OBType
from app.models.load_dispatch import LoadDispatchExecution
from app.schemas.load import LoadStatusUpdate
from app.schemas.load_dispatch_write import AllocationWrite, PlanWrite, PlanFinalize
from app.schemas.staging import StageRequest, VerificationStartRequest, VerificationScanRequest, VerificationCompleteRequest
from app.services import load_dispatch_write as writer, load_dispatch_gate as gate, staging


@pytest.fixture
def manifest(db, seed):
    actor = seed['admin']; wh = seed['warehouse']; customer = seed['customer']
    inbound = InboundRecord(inbound_no='TEST-IN', container_number='TEST-CONTAINER', warehouse_id=wh.id, customer_id=customer.id, created_by=actor.id)
    db.add(inbound); db.flush()
    lot = InventoryLot(lot_no='TEST-LOT', source_inbound_id=inbound.id, container_number=inbound.container_number, warehouse_id=wh.id, customer_id=customer.id, created_by=actor.id,
                       original_pallet_qty=4, available_pallet_qty=0, allocated_pallet_qty=4, original_carton_qty=0, available_carton_qty=0, original_weight_lbs=0, available_weight_lbs=0, original_cbm=0, available_cbm=0)
    load = Load(load_no='TEST-LOAD', warehouse_id=wh.id, status=LoadStatus.READY, dispatch_business_type='PRIVATE', created_by=actor.id)
    db.add_all([lot, load]); db.flush()
    order = OutboundOrder(ob_no='TEST-OB', warehouse_id=wh.id, customer_id=customer.id, created_by=actor.id, ob_type=OBType.STANDARD, status=3, load_id=load.id, dispatch_business_type='PRIVATE')
    db.add(order); db.flush()
    inv = OutboundInventoryAllocation(outbound_order_id=order.id, inventory_lot_id=lot.id, allocated_pallet_qty=4, created_by=actor.id)
    picking = PickingList(picking_no='TEST-PICK', outbound_order_id=order.id, status=3, created_by=actor.id, completed_by=actor.id)
    db.add_all([inv, picking]); db.flush()
    item = PickingListItem(picking_list_id=picking.id, outbound_allocation_id=inv.id, inventory_lot_id=lot.id, lot_no=lot.lot_no, container_number=lot.container_number, planned_pallet_qty=4, picked_pallet_qty=4)
    db.add(item); db.commit()
    return SimpleNamespace(load=load, order=order, inv=inv, lot=lot, item=item, actor=actor, location=seed['location'])


def final_plan(db, m):
    fact = writer.write_allocation(db, m.actor, m.load.id, AllocationWrite(inventory_allocation_id=m.inv.id, carton_qty=0, pallet_qty=4, operation_id='allocation-1'))
    plan = writer.create_plan(db, m.actor, m.load.id)
    plan = writer.replace_lines(db, m.actor, m.load.id, plan['id'], PlanWrite(expected_revision=plan['content_revision'], lines=[dict(allocation_id=fact['id'], carton_qty=0, pallet_qty=4)]))
    return writer.finalize_plan(db, m.actor, m.load.id, plan['id'], PlanFinalize(expected_revision=plan['content_revision']))


def execution(db, m):
    staging.stage(db, m.load, StageRequest(outbound_id=m.order.id, picking_item_id=m.item.id, staging_location_id=m.location.id, quantity=4, client_operation_id='stage-1'), m.actor.id)
    start = staging.verification_start(db, m.load, VerificationStartRequest(client_operation_id='start-1'), m.actor.id)
    run = start['verification_run_id']
    staging.verification_scan(db, m.load, VerificationScanRequest(verification_run_id=run, outbound_id=m.order.id, picking_item_id=m.item.id, quantity=4, client_operation_id='scan-1'), m.actor.id)
    staging.verification_complete(db, m.load, VerificationCompleteRequest(verification_run_id=run, client_operation_id='complete-1'), m.actor.id)


def request(plan, operation='dispatch-1'):
    return LoadStatusUpdate(status='DISPATCHED', operation_id=operation, plan_id=plan['id'], expected_revision=plan['content_revision'])


def synthetic_policies(monkeypatch):
    # Test-only substitute for UNCONFIRMED rules. No runtime writer/approval exists.
    monkeypatch.setattr(gate, 'policy_checks', lambda db, load: [gate.check(key, 'PASS', 'SYNTHETIC_TEST_POLICY', 'Test mechanics only', ['synthetic:test-only']) for key in ('documents', 'dispatch_approval', 'exceptions')])


def test_real_evidence_still_blocks_unconfirmed_policies(db, manifest):
    m = manifest; plan = final_plan(db, m); execution(db, m)
    result = gate.integrated_readiness(db, m.actor, m.load.id)
    assert not result.ready
    assert {c.key for c in result.checks if c.status == 'UNKNOWN'} == {'documents', 'dispatch_approval', 'exceptions'}
    assert next(c for c in result.checks if c.key == 'execution').status == 'PASS'
    with pytest.raises(HTTPException) as error: gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    assert error.value.status_code == 409
    assert m.load.status == LoadStatus.READY and m.order.status == 3
    assert db.query(LoadDispatchExecution).count() == 0


def test_transaction_success_and_exact_replay_with_synthetic_policy(db, manifest, monkeypatch):
    m = manifest; plan = final_plan(db, m); execution(db, m); synthetic_policies(monkeypatch)
    assert gate.integrated_readiness(db, m.actor, m.load.id).ready
    gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    assert m.load.status == LoadStatus.DISPATCHED and m.order.status == 4
    assert db.query(LoadDispatchExecution).count() == 1
    with pytest.raises(HTTPException): gate.dispatch_load(db, m.actor, m.load.id, request(plan, 'other'))


def test_missing_execution_and_stale_revision_block(db, manifest, monkeypatch):
    m = manifest; plan = final_plan(db, m); synthetic_policies(monkeypatch)
    with pytest.raises(HTTPException) as error: gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    assert 'LOADING_VERIFICATION_MISSING' in str(error.value.detail)
    payload = request(plan); payload.expected_revision += 1
    with pytest.raises(HTTPException) as error: gate.dispatch_load(db, m.actor, m.load.id, payload)
    assert error.value.detail == 'PLAN_REVISION_CONFLICT'


def test_failure_rolls_back_status_execution_and_audit(db, manifest, monkeypatch):
    from app.models import AuditLog
    from app.services import load as service
    m = manifest; plan = final_plan(db, m); execution(db, m); synthetic_policies(monkeypatch)
    monkeypatch.setattr(service, 'sync_load_notification', lambda *args: (_ for _ in ()).throw(RuntimeError('injected failure')))
    with pytest.raises(RuntimeError): gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    db.expire_all()
    assert m.load.status == LoadStatus.READY and m.order.status == 3
    assert db.query(LoadDispatchExecution).count() == 0
    assert db.query(AuditLog).filter_by(action='LOAD_DISPATCH').count() == 0


@pytest.mark.parametrize('tamper', ['warehouse', 'customer', 'business', 'quantity', 'ownership'])
def test_inventory_ownership_and_quantity_enforced_for_admin(db, manifest, tamper):
    m = manifest
    if tamper == 'warehouse':
        from app.models import Warehouse
        other = Warehouse(warehouse_code='OTHER', warehouse_name='Other', address='Test isolation', city='Test', state='CA', zip_code='00000'); db.add(other); db.flush(); m.lot.warehouse_id = other.id
    if tamper == 'customer':
        from app.models import Customer
        other = Customer(customer_code='OTHER', customer_name='Other'); db.add(other); db.flush(); m.lot.customer_id = other.id
    if tamper == 'business': m.order.dispatch_business_type = 'FBA'
    if tamper == 'quantity': m.inv.allocated_pallet_qty = 3
    if tamper == 'ownership': m.order.load_id = None
    db.commit()
    with pytest.raises(HTTPException): final_plan(db, m)


def test_final_plan_and_reservation_are_frozen(db, manifest):
    from app.services.outbound import require_allocation_mutable
    m = manifest; plan = final_plan(db, m)
    with pytest.raises(HTTPException): writer.replace_lines(db, m.actor, m.load.id, plan['id'], PlanWrite(expected_revision=plan['content_revision'], lines=[dict(allocation_id=1, carton_qty=0, pallet_qty=4)]))
    with pytest.raises(HTTPException): require_allocation_mutable(db, m.order)


def test_metadata_change_invalidates_verification(db, manifest):
    m = manifest; final_plan(db, m); execution(db, m)
    m.load.trailer_no = 'CHANGED'; db.commit()
    result = gate.integrated_readiness(db, m.actor, m.load.id)
    assert next(c for c in result.checks if c.key == 'execution').status == 'BLOCKED'


def test_viewer_cannot_dispatch_or_write(client, manifest, seed):
    from app.core.security import create_access_token
    client.headers['Authorization'] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    assert client.post(f'/api/v1/loads/{manifest.load.id}/plans').status_code == 403
    assert client.post(f'/api/v1/loads/{manifest.load.id}/status', json={'status':'DISPATCHED'}).status_code == 403


def fba_manifest(db, m):
    from app.models import FBAShipment, FBAInventoryAllocation
    shipment = FBAShipment(fba_no='TEST-FBA', amazon_fc_code='ONT8', warehouse_id=m.order.warehouse_id,
                           customer_id=m.order.customer_id, status=2, created_by=m.actor.id)
    db.add(shipment); db.flush()
    source = FBAInventoryAllocation(fba_shipment_id=shipment.id, inventory_lot_id=m.lot.id,
                                    allocated_pallet_qty=4, created_by=m.actor.id)
    db.add(source); db.flush()
    m.order.ob_type = OBType.FBA; m.order.dispatch_business_type = 'FBA'; m.load.dispatch_business_type = 'FBA'
    m.order.fba_shipment_id = shipment.id; m.inv.fba_allocation_id = source.id
    db.commit(); m.shipment = shipment; m.source = source
    return m


def test_fba_real_policies_block(db, manifest):
    test_real_evidence_still_blocks_unconfirmed_policies(db, fba_manifest(db, manifest))


def four_units(db, m):
    values = {'pallet_qty': 4, 'carton_qty': 40, 'weight_lbs': 400, 'cbm': 4}
    for unit, value in values.items():
        setattr(m.inv, f'allocated_{unit}', value)
        setattr(m.source, f'allocated_{unit}', value)
        setattr(m.lot, f'original_{unit}', value)
        setattr(m.lot, f'allocated_{unit}', value)
    db.commit()
    return values


def test_fba_dispatch_completion_conserves_all_units(db, manifest, monkeypatch):
    from app.services import outbound
    m = fba_manifest(db, manifest)
    plan = final_plan(db, m); execution(db, m); synthetic_policies(monkeypatch)
    gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    # Additional quantity dimensions exercise downstream conservation in isolation.
    values = four_units(db, m)
    outbound.change(db, m.order.id, 5, m.actor.id)
    for unit, value in values.items():
        assert getattr(m.inv, f'completed_{unit}') == value
        assert getattr(m.source, f'allocated_{unit}') == 0
        assert getattr(m.lot, f'allocated_{unit}') == 0
        assert getattr(m.lot, f'available_{unit}') == 0
    with pytest.raises(HTTPException): outbound.change(db, m.order.id, 5, m.actor.id)


def test_fba_upstream_release_waits_for_outbound_release(db, manifest):
    from app.services import outbound, fba
    from app.schemas.fba import ReleaseRequest as FBARelease
    from app.schemas.outbound import ReleaseRequest as OBRelease
    m = fba_manifest(db, manifest); values = four_units(db, m)
    with pytest.raises(HTTPException) as error: fba.release(db, m.shipment.id, m.source.id, FBARelease(), m.actor.id)
    assert 'FBA_RESERVATION_IN_USE' in str(error.value.detail)
    db.rollback()
    outbound.release(db, m.order.id, m.inv.id, OBRelease(), m.actor.id)
    for unit, value in values.items():
        assert getattr(m.lot, f'allocated_{unit}') == value
        assert getattr(m.source, f'allocated_{unit}') == value
    fba.release(db, m.shipment.id, m.source.id, FBARelease(), m.actor.id)
    for unit, value in values.items():
        assert getattr(m.lot, f'allocated_{unit}') == 0
        assert getattr(m.lot, f'available_{unit}') == value


def test_fba_ownership_and_completion_are_guarded(db, manifest):
    from app.services import fba
    from app.schemas.fba import FBAUpdate
    from app.models import Customer
    m = fba_manifest(db, manifest)
    other = Customer(customer_code='OTHER', customer_name='Other'); db.add(other); db.commit()
    with pytest.raises(HTTPException) as error:
        fba.update_fba(db, m.shipment, FBAUpdate(warehouse_id=m.shipment.warehouse_id, customer_id=other.id, amazon_fc_code='ONT8'), m.actor.id)
    assert error.value.detail == 'FBA_ALLOCATION_OWNERSHIP_IMMUTABLE'
    db.rollback(); m.shipment.status = 6; db.commit()
    with pytest.raises(HTTPException) as error: fba.change_status(db, m.shipment.id, 7, m.actor.id)
    assert 'FBA_RESERVATION_IN_USE' in str(error.value.detail)


@pytest.mark.parametrize('unit', ['pallet_qty', 'carton_qty', 'weight_lbs', 'cbm'])
def test_fba_source_cannot_be_over_reserved(db, manifest, unit):
    m = fba_manifest(db, manifest); four_units(db, m)
    setattr(m.source, f'allocated_{unit}', getattr(m.source, f'allocated_{unit}') - 1); db.commit()
    with pytest.raises(HTTPException): final_plan(db, m)


def test_corrupt_completion_fails_without_clamping_inventory(db, manifest, monkeypatch):
    from app.services import outbound
    m = fba_manifest(db, manifest)
    plan = final_plan(db, m); execution(db, m); synthetic_policies(monkeypatch)
    gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    m.lot.allocated_pallet_qty = 3; db.commit()
    with pytest.raises(HTTPException): outbound.change(db, m.order.id, 5, m.actor.id)
    db.rollback(); db.expire_all()
    assert m.order.status == 4 and m.inv.completed_pallet_qty == 0
    assert m.lot.allocated_pallet_qty == 3 and m.source.allocated_pallet_qty == 4


def test_shared_lot_cannot_hide_extra_private_reservations(db, manifest):
    m = fba_manifest(db, manifest)
    extra = OutboundOrder(ob_no='EXTRA-PRIVATE', warehouse_id=m.order.warehouse_id,
        customer_id=m.order.customer_id, created_by=m.actor.id, ob_type=OBType.STANDARD, status=3, dispatch_business_type='PRIVATE')
    db.add(extra); db.flush()
    db.add(OutboundInventoryAllocation(outbound_order_id=extra.id, inventory_lot_id=m.lot.id, allocated_pallet_qty=1, created_by=m.actor.id))
    db.commit()
    with pytest.raises(HTTPException) as error: final_plan(db, m)
    assert error.value.detail == 'INVENTORY_RESERVATION_QUANTITY_MISMATCH'


def test_execution_summary_restores_latest_batch_without_reopening_completed_run(db, manifest):
    m = manifest
    assert staging.execution_summary(db, m.load)['current_verification_run'] is None
    execution(db, m)
    summary = staging.execution_summary(db, m.load)
    completed_run = summary['current_verification_run']
    assert completed_run['status'] == 'COMPLETE'
    assert summary['verification_complete'] and summary['manifest_matches']
    start = staging.verification_start(db, m.load, VerificationStartRequest(client_operation_id='start-2'), m.actor.id)
    db.expire_all()
    summary = staging.execution_summary(db, m.load)
    assert summary['current_verification_run'] == {'id': start['verification_run_id'], 'status': 'STARTED'}
    assert completed_run['id'] != start['verification_run_id']
    # The projection does not change dispatch evidence from the prior completion.
    assert summary['verification_complete'] and summary['manifest_matches']
    with pytest.raises(HTTPException) as error:
        staging.verification_scan(db, m.load, VerificationScanRequest(verification_run_id=completed_run['id'], outbound_id=m.order.id, picking_item_id=m.item.id, quantity=1, client_operation_id='closed-scan'), m.actor.id)
    assert error.value.status_code == 409
