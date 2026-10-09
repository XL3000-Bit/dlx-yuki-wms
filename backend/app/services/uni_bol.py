"""Local OB BOL aggregate. Cargo identity, shipping documents and stock stay distinct."""
from datetime import datetime, UTC
from decimal import Decimal
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text, or_, func
from app.models import (UniBol, FBAShipment, OutboundOrder, InventoryLot, CargoBOL,
                        Carrier, Warehouse, Customer, AuditLog, BOL, PickingList,
                        OutboundInventoryAllocation, FBAInventoryAllocation, OperationalDocument)
from app.schemas.fba import FBACreate, AllocateRequest as FBAAllocate, ReleaseRequest as FBARelease
from app.schemas.outbound import OBCreate, AllocateRequest as OBAllocate, CompleteRequest, ReleaseRequest
from app.schemas.uni_bol import BolDetails
from app.services import fba, outbound, picking_bol
from app.services.access_policy import scoped_statement, assert_customer_access, assert_warehouse_access
from app.services.history_policy import require_live_record, history_job_ids
from app.services.dispatch_readiness import get_dispatch_readiness
from app.models.operational_document import DocumentType, DocumentStatus
from app.services import operational_document
from app.services.document_storage import LocalDocumentStorage

QUANTITIES = ('pallet_qty', 'carton_qty', 'weight_lbs', 'cbm')
# These metadata fields remain editable on observed In Transit and Delivered pages.
POST_SHIPMENT_EDITABLE = frozenset({
    'seal_number', 'pro_number', 'payment', 'title_header', 'title_body',
    'billing_to', 'remark', 'customer_remark', 'internal_remark', 'urgent_level',
})


def quantities(row, prefix):
    return {key: getattr(row, prefix + key) for key in QUANTITIES}


def remaining(row):
    return {key: getattr(row, 'allocated_' + key) - getattr(row, 'completed_' + key) for key in QUANTITIES}


def allocations(db, ob):
    return list(db.scalars(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id == ob.id).order_by(OutboundInventoryAllocation.inventory_lot_id)))


def validate_quantities(values, available):
    if values['pallet_qty'] <= 0 or values['carton_qty'] <= 0 or any(values[k] < 0 or values[k] > available[k] for k in QUANTITIES):
        raise HTTPException(409, 'Actual quantities must be positive and within the remaining reservation in all four units')
    # No conversion formula is assumed. A final carton/pallet must also exhaust its other quantities.
    if (values['carton_qty'] == available['carton_qty'] or values['pallet_qty'] == available['pallet_qty']) and values != available:
        raise HTTPException(422, 'The final cartons/pallets must include all remaining weight, volume and quantities')


def sync_picking(db, ob, user, closed=False):
    by_id = {x.id: x for x in allocations(db, ob)}
    seen = set()
    for picking in db.scalars(select(PickingList).where(PickingList.outbound_order_id == ob.id, PickingList.status != 4)):
        for item in picking.items:
            row = by_id[item.outbound_allocation_id]
            for key in QUANTITIES:
                setattr(item, 'planned_' + key, getattr(row, 'allocated_' + key) if row.id not in seen else 0)
                setattr(item, 'picked_' + key, getattr(row, 'completed_' + key) if row.id not in seen else 0)
            seen.add(row.id)
        picking.status = 3 if closed else 2
        if closed:
            picking.completed_at = datetime.now(UTC)
            picking.completed_by = user.id
    db.flush()


def close_outbound(db, ob, user):
    sync_picking(db, ob, user, True)
    outbound.change(db, ob.id, 4, user.id, commit=False)
    outbound.change(db, ob.id, 5, user.id, commit=False)


def scoped(db, user):
    return scoped_statement(select(UniBol).join(OutboundOrder, UniBol.outbound_order_id == OutboundOrder.id),
                            user, warehouse_column=OutboundOrder.warehouse_id, customer_column=OutboundOrder.customer_id)


def get(db, user, identity, version=None):
    stmt = scoped(db, user).where(UniBol.id == identity)
    if version is not None:
        stmt = stmt.with_for_update(of=UniBol).execution_options(populate_existing=True)
    record = db.scalar(stmt)
    if not record:
        raise HTTPException(404, 'OB BOL not found')
    if version is not None and record.version != version:
        raise HTTPException(409, 'BOL changed. Refresh before continuing.')
    return record


def serialize(db, record, detail=False):
    ob = db.get(OutboundOrder, record.outbound_order_id)
    cargo = db.scalar(select(CargoBOL).where(CargoBOL.fba_shipment_id == record.fba_shipment_id))
    lines = list(db.scalars(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id == ob.id)))
    loads = []
    for line in lines:
        lot = db.get(InventoryLot, line.inventory_lot_id)
        canceled = {k: sum(Decimal(str(x.get(k, 0))) for event in (record.workflow or {}).get('cancellations', []) for x in event['lines'] if x['inventory_lot_id'] == lot.id) for k in QUANTITIES}
        if not any((line.allocated_pallet_qty, line.allocated_carton_qty, line.completed_pallet_qty, line.completed_carton_qty, canceled['carton_qty'])):
            continue
        source = lot.source_inbound
        receipt = ((source.source_metadata or {}).get('ocean_receipt') or {}) if source else {}
        loads.append(dict(id=lot.id, allocation_id=line.id, load_id=lot.lot_no, container_number=lot.container_number,
                          marking=lot.marking, delivery_code=lot.fc_code,
                          location=lot.location.location_code if lot.location else None,
                          book_qty=line.allocated_carton_qty+canceled['carton_qty'], actual_qty=line.allocated_carton_qty,
                          current_qty=line.allocated_carton_qty-line.completed_carton_qty,
                          weight_lbs=line.allocated_weight_lbs, cbm=line.allocated_cbm,
                          remaining_weight_lbs=line.allocated_weight_lbs-line.completed_weight_lbs,
                          remaining_cbm=line.allocated_cbm-line.completed_cbm,
                          shipped_qty=line.completed_carton_qty, canceled_qty=canceled['carton_qty'],
                          canceled_pallets=canceled['pallet_qty'], status='In WHS' if line.allocated_carton_qty > line.completed_carton_qty else ('Shipped' if line.completed_carton_qty else 'Canceled'),
                          receiver_shipment_id=source.fba_reference if source else None,
                          receiver_reference_id=source.po_number if source else None,
                          estimate_pallets=receipt.get('estimated_pallets'), markup_pallets=receipt.get('markup_pallets'),
                          inbound_pallets=lot.original_pallet_qty, whs_pallets=line.allocated_pallet_qty-line.completed_pallet_qty,
                          shipout_pallets=line.completed_pallet_qty, remaining_pallets=line.allocated_pallet_qty-line.completed_pallet_qty))
    data = dict(id=record.id, bol_no=cargo.bol_no if cargo else None, ob_no=(record.dispatch_ob_no if record.dispatch_ob_no is not None else ob.ob_no),
                outbound_order_id=ob.id, fba_shipment_id=record.fba_shipment_id,
                status=record.status, version=record.version, type='FBA',
                customer_id=ob.customer_id, customer=ob.customer.customer_name if ob.customer else None,
                warehouse_id=ob.warehouse_id, pickup=ob.warehouse.warehouse_name,
                delivery_code=ob.fc_code, created_at=record.created_at, updated_at=record.updated_at,
                created_by=ob.creator.display_name if hasattr(ob, 'creator') and ob.creator else None,
                loads_count=len(loads), whs_pallets=sum(x['whs_pallets'] for x in loads),
                cartons=sum(x['book_qty'] for x in loads),
                details={key: value for key, value in (record.details or {}).items() if key in BolDetails.model_fields},
                delivery_time=(record.details or {}).get('delivery_time'),
                carrier=db.get(Carrier, ob.carrier_id).carrier_name if ob.carrier_id else None,
                actual_pickup_time=(record.workflow or {}).get('first_shipout_time') or ob.actual_outbound_time or ob.dispatched_at,
                remaining_qty=sum(x['current_qty'] for x in loads), shipped_qty=sum(x['shipped_qty'] for x in loads),
                pod_status=(record.workflow or {}).get('pod_status', 'Awaiting Upload' if record.status in ('In Transit', 'Delivered') else 'Not Ready'),
                group_status=('Partial In WHS' if any(x['shipped_qty'] > 0 for x in loads) else 'In WHS') if any(x['current_qty'] > 0 for x in loads) else 'Not In WHS',
                workflow=record.workflow or {})
    data['loads'] = loads
    if detail:
        data['pod_documents'] = [dict(id=d.id, original_filename=d.original_filename, version=d.version, status=d.status, created_at=d.created_at) for d in db.scalars(select(OperationalDocument).where(OperationalDocument.outbound_id == ob.id, OperationalDocument.document_type == DocumentType.POD).order_by(OperationalDocument.id.desc()))]
        data['documents'] = [dict(id=b.id, bol_no=b.bol_no, status=b.status) for b in db.scalars(select(BOL).where(BOL.outbound_order_id == ob.id))]
        data['activities'] = [dict(action=a.action, at=a.created_at, data=a.after_data) for a in db.scalars(
            select(AuditLog).where(AuditLog.entity_type == 'UNI_BOL', AuditLog.entity_id == record.id).order_by(AuditLog.id.desc()))]
    return jsonable_encoder(data)


def audit(db, user, record, action):
    db.add(AuditLog(user_id=user.id, action=action, entity_type='UNI_BOL', entity_id=record.id,
                    after_data={'status': record.status, 'version': record.version}))


def sync_details(db, record, details):
    ob = db.get(OutboundOrder, record.outbound_order_id)
    if details.carrier_id is not None:
        carrier = db.get(Carrier, details.carrier_id)
        if carrier is None or not carrier.is_active:
            raise HTTPException(422, 'Select an active OTR Carrier')
    record.details = details.model_dump(mode='json')
    ob.carrier_id = details.carrier_id
    ob.schedule_pickup_at = details.scheduled_pickup_time
    ob.delivery_appointment_time = details.delivery_appointment_time
    ob.reference_no = details.customer_reference
    ob.appointment_reference = details.delivery_appointment
    ob.truck_type = details.shipping_mode
    ob.pickup_location = db.get(Warehouse, ob.warehouse_id).warehouse_name
    ob.remark = details.remark
    shipment = db.get(FBAShipment, record.fba_shipment_id)
    shipment.carrier_id = details.carrier_id
    shipment.scheduled_pickup_at = details.scheduled_pickup_time
    shipment.appointment_time = details.delivery_appointment_time


def create(db, user, payload):
    assert_warehouse_access(user, payload.warehouse_id)
    assert_customer_access(user, payload.customer_id)
    for model, identity in ((Warehouse, payload.warehouse_id), (Customer, payload.customer_id)):
        master = db.get(model, identity)
        if master is None or not master.is_active:
            raise HTTPException(422, 'Select active warehouse and customer')
    db.info['uni_workflow'] = True
    shipment = fba.create_fba(db, FBACreate(warehouse_id=payload.warehouse_id, customer_id=payload.customer_id,
                               amazon_fc_code=payload.delivery_code), user.id, commit=False)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('uni-ob-number'))"))
    ob = outbound.create_ob(db, OBCreate(warehouse_id=payload.warehouse_id, customer_id=payload.customer_id,
                             fba_shipment_id=shipment.id, ob_type='FBA', fc_code=shipment.amazon_fc_code), user.id, commit=False)
    record = UniBol(fba_shipment_id=shipment.id, outbound_order_id=ob.id, status='Pre', version=1, details={})
    db.add(record)
    db.flush()
    sync_details(db, record, payload.details)
    audit(db, user, record, 'CREATE')
    db.commit()
    return serialize(db, record, True)


def update(db, user, identity, payload):
    record = get(db, user, identity, payload.version)
    if record.status not in ('Pre', 'In Transit', 'Delivered'):
        raise HTTPException(409, 'This BOL status does not allow editing')
    if record.status in ('In Transit', 'Delivered'):
        previous = BolDetails.model_validate({k: v for k, v in record.details.items() if k in BolDetails.model_fields})
        changed = {key for key in BolDetails.model_fields if getattr(previous, key) != getattr(payload.details, key)}
        if changed - POST_SHIPMENT_EDITABLE:
            raise HTTPException(409, f'These fields are read-only while {record.status}: ' + ', '.join(sorted(changed - POST_SHIPMENT_EDITABLE)))
    db.info['uni_workflow'] = True
    if record.status == 'Pre':
        sync_details(db, record, payload.details)
    else:
        # Metadata saves never rewrite shipment appointments, allocations or stock.
        values = payload.details.model_dump(mode='json')
        record.details = {**record.details, **{key: values[key] for key in POST_SHIPMENT_EDITABLE}}
        db.get(OutboundOrder, record.outbound_order_id).remark = payload.details.remark
    record.version += 1
    audit(db, user, record, 'SAVE')
    db.commit()
    return serialize(db, record, True)


def candidates(db, user, identity, q=''):
    record = get(db, user, identity)
    ob = db.get(OutboundOrder, record.outbound_order_id)
    stmt = scoped_statement(select(InventoryLot), user, warehouse_column=InventoryLot.warehouse_id, customer_column=InventoryLot.customer_id).where(
        InventoryLot.warehouse_id == ob.warehouse_id, InventoryLot.customer_id == ob.customer_id,
        func.upper(InventoryLot.fc_code) == ob.fc_code.upper(), InventoryLot.available_pallet_qty > 0,
        InventoryLot.available_carton_qty > 0)
    if q:
        stmt = stmt.where(or_(InventoryLot.lot_no.ilike(f'%{q}%'), InventoryLot.container_number.ilike(f'%{q}%'), InventoryLot.marking.ilike(f'%{q}%')))
    history = history_job_ids(db)
    result = []
    for lot in db.scalars(stmt.order_by(InventoryLot.id).limit(500)):
        if lot.source_inbound and lot.source_inbound.import_job_id in history:
            continue
        result.append(dict(id=lot.id, load_id=lot.lot_no, container_number=lot.container_number,
                           marking=lot.marking, delivery_code=lot.fc_code, qty=lot.available_carton_qty,
                           pallets=lot.available_pallet_qty, weight_lbs=lot.available_weight_lbs, cbm=lot.available_cbm,
                           location=lot.location.location_code if lot.location else None, status='WHS Received'))
    return jsonable_encoder(result)


def select_loads(db, user, identity, payload):
    record = get(db, user, identity, payload.version)
    if record.status != 'Pre':
        raise HTTPException(409, 'Loads can only be selected in Pre')
    ids = payload.inventory_lot_ids or [x.inventory_lot_id for x in payload.lines]
    if not ids or (payload.inventory_lot_ids and payload.lines):
        raise HTTPException(422, 'Choose either complete loads or explicit quantities')
    if len(set(ids)) != len(ids):
        raise HTTPException(422, 'Duplicate loads')
    db.info['uni_workflow'] = True
    ob = outbound.get_ob(db, record.outbound_order_id, True, user=user)
    selected = {x.inventory_lot_id: x for x in payload.lines}
    for lot_id in sorted(ids):
        lot = db.scalar(select(InventoryLot).where(InventoryLot.id == lot_id).with_for_update().execution_options(populate_existing=True))
        if not lot or lot.warehouse_id != ob.warehouse_id or lot.customer_id != ob.customer_id or (lot.fc_code or '').upper() != ob.fc_code.upper():
            raise HTTPException(422, 'Loads must match this BOL warehouse, customer and Delivery Code')
        if lot.source_inbound:
            require_live_record(db, lot.source_inbound)
        if lot.available_pallet_qty <= 0 or lot.available_carton_qty <= 0:
            raise HTTPException(409, 'Load is no longer available')
        available = quantities(lot, 'available_')
        values = selected[lot_id].model_dump(exclude={'inventory_lot_id'}) if lot_id in selected else available
        validate_quantities(values, available)
        allocation = fba.allocate(db, record.fba_shipment_id, FBAAllocate(inventory_lot_id=lot.id, **values), user.id, commit=False)
        outbound.allocate(db, ob.id, OBAllocate(inventory_lot_id=lot.id, fba_allocation_id=allocation.id, **values), user.id, commit=False)
    record.version += 1
    audit(db, user, record, 'SELECT_LOADS')
    db.commit()
    return serialize(db, record, True)


def action(db, user, identity, payload):
    record = get(db, user, identity, payload.version)
    allowed = {'confirm': ('Pre',), 'shipout': ('Confirmed', 'In Transit'), 'deliver': ('In Transit',), 'cancel': ('Pre', 'Confirmed', 'In Transit')}
    if record.status not in allowed[payload.action]:
        raise HTTPException(409, f'{payload.action} is not available in {record.status}')
    db.info['uni_workflow'] = True
    ob = outbound.get_ob(db, record.outbound_order_id, True, user=user)
    shipment = fba.get_fba(db, record.fba_shipment_id, True, user=user)
    flow = deepcopy(record.workflow or {})
    if payload.request_id and payload.request_id in flow.get('request_ids', []):
        raise HTTPException(409, 'This operation was already applied; refresh to see the result')
    rows = allocations(db, ob)
    if payload.action == 'confirm':
        if not ob.carrier_id:
            raise HTTPException(422, 'Select OTR Carrier before Confirm BOL')
        outbound.change(db, ob.id, 3, user.id, commit=False)
        for document in db.scalars(select(BOL).where(BOL.outbound_order_id == ob.id)):
            if record.details.get('pickup_address'):
                document.ship_from_address = record.details['pickup_address']
            if record.details.get('delivery_address'):
                document.ship_to_address = record.details['delivery_address']
            document.special_instructions = record.details.get('remark', '')
        record.status = 'Confirmed'
        shipment.status = 3
    elif payload.action == 'shipout':
        if not payload.confirm_all_picked:
            raise HTTPException(422, 'Confirm actual quantities and all cargo picked before shipout')
        if payload.lines and not payload.request_id:
            raise HTTPException(422, 'Partial shipout requires a unique request_id')
        failures = [x.reason for x in get_dispatch_readiness(db, ob).checks if not x.passed and x.key != 'picking']
        if failures:
            raise HTTPException(409, '; '.join(failures))
        selected = {x.inventory_lot_id: x for x in payload.lines}
        if len(selected) != len(payload.lines) or not set(selected).issubset({x.inventory_lot_id for x in rows}):
            raise HTTPException(422, 'Duplicate or unrelated loads')
        plan = []
        for row in rows:
            available = remaining(row)
            if selected and row.inventory_lot_id not in selected: continue
            if not any(available.values()):
                if row.inventory_lot_id in selected: raise HTTPException(409, 'Selected load has no remaining cargo')
                continue
            values = selected[row.inventory_lot_id].model_dump(exclude={'inventory_lot_id'}) if selected else available
            validate_quantities(values, available)
            plan.append((row, values))
        if not plan: raise HTTPException(409, 'No remaining cargo to ship')
        for row, values in plan:
            outbound.complete_partial(db, ob, user.id, CompleteRequest(allocation_id=row.id, request_id=f"UNI:{record.id}:{payload.request_id or record.version}:{row.id}", **values))
        closed = not any(any(remaining(x).values()) for x in rows)
        if closed: close_outbound(db, ob, user)
        else: sync_picking(db, ob, user)
        now = datetime.now(UTC).isoformat()
        flow.setdefault('shipouts', []).append(dict(at=now, operator=user.display_name, request_id=payload.request_id,
            remark=payload.remark, lines=[dict(inventory_lot_id=r.inventory_lot_id, **{k: str(v) for k,v in vals.items()}) for r, vals in plan]))
        flow.setdefault('first_shipout_time', now)
        flow.setdefault('pod_status', 'Awaiting Upload')
        record.status = 'In Transit'
        shipment.status = 5
    elif payload.action == 'deliver':
        if any(any(remaining(x).values()) for x in rows):
            raise HTTPException(409, 'Ship or cancel the remaining cargo before Confirm Delivery')
        record.status = 'Delivered'
        record.details = {**record.details, 'delivery_time': datetime.now(UTC).isoformat()}
        shipment.status = 6
    else:
        pending = [(x, remaining(x)) for x in rows if any(remaining(x).values())]
        if not pending and record.status == 'In Transit': raise HTTPException(409, 'No remaining reservation to cancel')
        had_shipout = any(x.completed_carton_qty > 0 for x in rows)
        if had_shipout:
            for row, vals in pending:
                outbound.release(db, ob.id, row.id, ReleaseRequest(**vals), user.id, commit=False)
        else: outbound.change(db, ob.id, 6, user.id, commit=False)
        db.flush()
        for allocation in db.scalars(select(FBAInventoryAllocation).where(FBAInventoryAllocation.fba_shipment_id == shipment.id)):
            if any((allocation.allocated_pallet_qty, allocation.allocated_carton_qty, allocation.allocated_weight_lbs, allocation.allocated_cbm)):
                fba.release(db, shipment.id, allocation.id, FBARelease(), user.id, commit=False)
        flow.setdefault('cancellations', []).append(dict(at=datetime.now(UTC).isoformat(), operator=user.display_name, remark=payload.remark,
            lines=[dict(inventory_lot_id=r.inventory_lot_id, **{k: str(v) for k,v in vals.items()}) for r, vals in pending]))
        if had_shipout:
            close_outbound(db, ob, user)
        else:
            for document in db.scalars(select(BOL).where(BOL.outbound_order_id == ob.id)): document.status = 4
            for picking in db.scalars(select(PickingList).where(PickingList.outbound_order_id == ob.id)): picking.status = 4
            record.status = 'Canceled'
            shipment.status = 9
    if payload.request_id: flow.setdefault('request_ids', []).append(payload.request_id)
    record.workflow = flow
    record.version += 1
    audit(db, user, record, payload.action.upper())
    db.commit()
    return serialize(db, record, True)


def pod_candidates(db, user, ob_no):
    number = ob_no.strip()
    if not number:
        return []
    stmt = scoped(db, user).where(func.lower(func.coalesce(UniBol.dispatch_ob_no, OutboundOrder.ob_no)) == number.lower())
    return [serialize(db, row) for row in db.scalars(stmt.order_by(UniBol.id))]


def pod_checksum(upload):
    head = upload.file.read(16); upload.file.seek(0)
    ext = Path(upload.filename or '').suffix.lower()
    valid = (ext == '.pdf' and head.startswith(b'%PDF')) or (ext == '.png' and head.startswith(b'\x89PNG\r\n\x1a\n')) or (ext in ('.jpg', '.jpeg') and head.startswith(b'\xff\xd8\xff'))
    if not valid: raise HTTPException(415, 'Upload a PDF, PNG or JPEG POD with matching file content')
    from app.core.config import settings
    digest = sha256(); size = 0
    while chunk := upload.file.read(1024 * 1024):
        size += len(chunk)
        if size > min(settings.document_max_upload_bytes, 3 * 1024 * 1024):
            raise HTTPException(413, 'Maximum upload document size: 3 MB.')
        digest.update(chunk)
    upload.file.seek(0)
    return digest.hexdigest()


def save_pod_documents(db, user, records, upload, metadata=None):
    checksum = pod_checksum(upload)
    for record in records:
        if record.status not in ('In Transit', 'Delivered'):
            raise HTTPException(409, 'POD can be uploaded after shipout')
        if db.scalar(select(OperationalDocument.id).where(OperationalDocument.outbound_id == record.outbound_order_id,
                OperationalDocument.document_type == DocumentType.POD, OperationalDocument.checksum_sha256 == checksum)):
            raise HTTPException(409, 'This POD file was already uploaded for a selected BOL')
    db.info['uni_workflow'] = True
    stored_keys = []
    try:
        for record in records:
            upload.file.seek(0)
            document = operational_document.upload_document(db, user, upload, DocumentType.POD, {'outbound_id': record.outbound_order_id}, commit=False)
            stored_keys.append(document.storage_key)
            flow = deepcopy(record.workflow or {})
            flow.update(pod_status='Awaiting Verify', pod_document_id=document.id)
            flow.setdefault('pod_uploads', []).append({**(metadata or {}), 'document_id': document.id,
                'at': datetime.now(UTC).isoformat(), 'operator': user.display_name})
            record.workflow = flow
            record.version += 1
            audit(db, user, record, 'UPLOAD_POD')
        db.commit()
    except Exception:
        db.rollback()
        for key in stored_keys:
            LocalDocumentStorage().delete(key)
        raise
    return [serialize(db, record, True) for record in records]


def upload_pod(db, user, identity, version, upload, metadata=None):
    record = get(db, user, identity, version)
    return save_pod_documents(db, user, [record], upload, metadata)[0]


def upload_batch_pod(db, user, payload, upload):
    ids = [item.id for item in payload.bols]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, 'Select each BOL only once')
    # A consistent lock order prevents conflicting batch submissions from deadlocking.
    records = [get(db, user, item.id, item.version) for item in sorted(payload.bols, key=lambda item: item.id)]
    for record in records:
        ob = db.get(OutboundOrder, record.outbound_order_id)
        if ((record.dispatch_ob_no if record.dispatch_ob_no is not None else ob.ob_no)).lower() != payload.ob_no.lower():
            raise HTTPException(409, 'Selected BOL does not belong to this OB. Search again.')
    return save_pod_documents(db, user, records, upload, {
        'ob_no': payload.ob_no, 'delivery_date': payload.delivery_date.isoformat(),
        'delivery_appointment': payload.delivery_appointment})


def review_pod(db, user, identity, payload):
    record = get(db, user, identity, payload.version)
    flow = deepcopy(record.workflow or {})
    document = operational_document.get_document(db, user, payload.document_id)
    if flow.get('pod_status') != 'Awaiting Verify' or flow.get('pod_document_id') != document.id or document.status != DocumentStatus.AVAILABLE:
        raise HTTPException(409, 'Only the current pending POD can be reviewed')
    if payload.result == 'Exception' and not payload.remark.strip(): raise HTTPException(422, 'Explain the POD exception')
    flow['pod_status'] = payload.result
    flow.setdefault('pod_reviews', []).append(dict(document_id=document.id, result=payload.result, remark=payload.remark, at=datetime.now(UTC).isoformat(), operator=user.display_name))
    record.workflow = flow; record.version += 1
    audit(db, user, record, 'POD_' + payload.result.upper())
    db.commit()
    return serialize(db, record, True)


def dispatch_target(db, user, identity, allow_unassigned=False):
    stmt = scoped_statement(select(OutboundOrder), user,
        warehouse_column=OutboundOrder.warehouse_id, customer_column=OutboundOrder.customer_id)
    ob = db.scalar(stmt.where(OutboundOrder.id == identity, OutboundOrder.ob_type.in_(('FBA', 'TBD') if allow_unassigned else ('FBA',))))
    if not ob:
        raise HTTPException(404, 'FBA OB not found')
    return ob


def dispatch_bols(db, user, identity, pool=False, page=1, per_page=20):
    ob = dispatch_target(db, user, identity, allow_unassigned=not pool)
    effective = func.coalesce(UniBol.dispatch_ob_no, OutboundOrder.ob_no)
    stmt = scoped(db, user).where(effective == ('' if pool else ob.ob_no))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'data': [serialize(db, r) for r in db.scalars(stmt.order_by(UniBol.id.desc()).offset((page-1)*per_page).limit(per_page))],
            'total': total, 'page': page, 'per_page': per_page}


def dispatch_membership(db, user, identity, payload):
    ob = dispatch_target(db, user, identity)
    if len({b.id for b in payload.bols}) != len(payload.bols):
        raise HTTPException(422, 'Duplicate BOL selection')
    records = []
    for selected in sorted(payload.bols, key=lambda b: b.id):
        record = get(db, user, selected.id, selected.version)
        owner = db.get(OutboundOrder, record.outbound_order_id)
        current = record.dispatch_ob_no if record.dispatch_ob_no is not None else owner.ob_no
        if payload.action == 'join' and current:
            raise HTTPException(409, 'Remove BOL from its current OB before joining another OB')
        if payload.action == 'remove' and current != ob.ob_no:
            raise HTTPException(409, 'BOL is not associated with this OB')
        records.append(record)
    # Dispatch membership never changes inventory ownership, allocations or business status.
    for record in records:
        record.dispatch_ob_no = ob.ob_no if payload.action == 'join' else ''
        record.version += 1
    db.commit()
    return {'data': [serialize(db, r) for r in records]}
