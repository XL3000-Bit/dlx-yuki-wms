"""Container receiving, with scoped batches and separate planned/actual quantities."""
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, case

from app.models import AuditLog, CargoBOL, InboundRecord, WarehouseLocation
from app.models.user import UserRole
from app.services.access_policy import customer_clause, warehouse_clause
from app.services.history_policy import history_job_ids, require_live_record
from app.services.inbound import _read, get_inbound
from app.utils.business_time import get_business_today

KEY = "ocean_receipt"


def list_shipments(db, user, q='', status=None, date_from=None, date_to=None, page=1, per_page=50, filters=None):
    r = InboundRecord
    stmt = select(func.min(r.id).label('id'), r.container_number, r.warehouse_id,
                  r.unload_date, func.count(r.id).label('loads_count'),
                  func.sum(r.carton_qty).label('pieces'), func.min(r.status).label('status'),
                  func.sum(case((r.status.in_([3, 4]), 1), else_=0)).label('putaway_count')).group_by(
                      r.container_number, r.warehouse_id, r.unload_date)
    for clause in (warehouse_clause(user, r.warehouse_id), customer_clause(user, r.customer_id)):
        if clause is not None:
            stmt = stmt.where(clause)
    if q:
        stmt = stmt.where(r.container_number.ilike(f'%{q}%'))
    if date_from:
        stmt = stmt.where(r.unload_date >= date_from)
    if date_to:
        stmt = stmt.where(r.unload_date <= date_to)
    if status is not None:
        stmt = stmt.having(func.min(r.status) == status)
    grouped = stmt.subquery()
    stmt = select(grouped, r.source_metadata).join(r, r.id == grouped.c.id)
    options = {}
    for key in ('size', 'trucker', 'team'):
        column = r.source_metadata['ocean_shipment'][key].as_string()
        options[key] = sorted({v for v in db.scalars(stmt.with_only_columns(column).distinct()) if v})
    ranges = {'scheduled_from': ('scheduled_delivery_date', True), 'scheduled_to': ('scheduled_delivery_date', False),
              'pod_eta_from': ('pod_eta', True), 'pod_eta_to': ('pod_eta', False),
              'appointment_from': ('appointment', True), 'appointment_to': ('appointment', False)}
    for key, value in (filters or {}).items():
        if value is not None and value != '':
            if key == 'list_status':
                continue
            if key in ranges:
                field, lower = ranges[key]
                # ISO date prefix retains date-time values and includes the full end day.
                column = func.substr(r.source_metadata['ocean_shipment'][field].as_string(), 1, 10)
                stmt = stmt.where(column >= str(value) if lower else column <= str(value))
                continue
            column = r.source_metadata['ocean_shipment'][key].as_string()
            if key in ('printed', 'empty_reported', 'released', 'outbound_fully_pod'):
                stmt = stmt.where(func.coalesce(column, 'false') == str(value).lower())
            elif key in ('transport_status', 'container_status', 'size', 'trucker', 'team'):
                stmt = stmt.where(func.coalesce(column, 'TBD' if key == 'transport_status' else '') .in_(str(value).split('|')))
            else: stmt = stmt.where(column.ilike(f'%{value}%'))
    count_rows = stmt.with_only_columns(r.source_metadata['ocean_shipment']['list_status'].as_string().label('list_status')).subquery()
    counts = dict(db.execute(select(count_rows.c.list_status, func.count()).group_by(count_rows.c.list_status)).all())
    counts['Total'] = sum(counts.values())
    counts['Unclassified'] = counts.pop(None, 0)
    if (filters or {}).get('list_status'):
        stmt = stmt.where(r.source_metadata['ocean_shipment']['list_status'].as_string().in_(filters['list_status'].split('|')))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    data = []
    for row in db.execute(stmt.order_by(grouped.c.id.desc()).offset((page-1)*per_page).limit(per_page)).mappings():
        item = dict(row)
        item['shipment'] = (item.pop('source_metadata') or {}).get('ocean_shipment', {'version': 0, 'transport_status': 'TBD'})
        data.append(item)
    return jsonable_encoder({'data': data, 'total': total, 'page': page, 'per_page': per_page, 'counts': counts, 'options': options})


def shipment_rows(db, user, anchor_id, *, lock=False):
    anchor = get_inbound(db, anchor_id, user)
    # Reused containers on different unloading dates are separate receiving visits.
    stmt = select(InboundRecord).where(
        InboundRecord.container_number == anchor.container_number,
        InboundRecord.warehouse_id == anchor.warehouse_id,
        InboundRecord.unload_date == anchor.unload_date,
    )
    for clause in (warehouse_clause(user, InboundRecord.warehouse_id), customer_clause(user, InboundRecord.customer_id)):
        if clause is not None:
            stmt = stmt.where(clause)
    stmt = stmt.order_by(InboundRecord.id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(stmt))


def read_shipment(db, user, anchor_id):
    rows = shipment_rows(db, user, anchor_id)
    history = history_job_ids(db)
    bols = {b.inbound_id: b.bol_no for b in db.scalars(select(CargoBOL).where(CargoBOL.inbound_id.in_([r.id for r in rows])))}
    data = []
    for row in rows:
        receipt = dict((row.source_metadata or {}).get(KEY) or {})
        receipt.setdefault("version", 0)
        receipt.setdefault("expected_qty", str(row.carton_qty))
        receipt.setdefault("expected_pallets", str(row.pallet_qty))
        receipt.setdefault("location_id", row.location_id)
        if row.status in (2, 3, 4):
            receipt.setdefault("received_qty", str(row.carton_qty))
            receipt.setdefault("inbound_pallets", str(row.pallet_qty))
        lot = row.inventory_lot
        inventory = None if not lot else dict(id=lot.id, current_qty=lot.available_carton_qty + lot.allocated_carton_qty + lot.hold_carton_qty,
            whs_pallets=lot.available_pallet_qty + lot.allocated_pallet_qty + lot.hold_pallet_qty,
            shipout_pallets=lot.original_pallet_qty-lot.available_pallet_qty-lot.allocated_pallet_qty-lot.hold_pallet_qty,
            remaining_pallets=lot.available_pallet_qty, reserved_pallets=lot.allocated_pallet_qty,
            available_qty=lot.available_carton_qty, reserved_qty=lot.allocated_carton_qty)
        data.append({"inbound": _read(row), "receipt": receipt, "inventory": inventory, "cargo_bol_no": bols.get(row.id),
                     "can_putaway": user.role in {UserRole.ADMIN, UserRole.MANAGER, UserRole.INBOUND, UserRole.WAREHOUSE} and row.status == 2 and row.inventory_lot is None and row.import_job_id not in history,
                     "editable": user.role in {UserRole.ADMIN, UserRole.MANAGER, UserRole.INBOUND, UserRole.WAREHOUSE} and row.status in (0, 1) and row.inventory_lot is None and row.import_job_id not in history})
    return {"data": data, "shipment": (rows[0].source_metadata or {}).get('ocean_shipment', {'version': 0, 'transport_status': 'TBD'}) if rows else {}, "can_upload": user.role in {UserRole.ADMIN, UserRole.MANAGER, UserRole.INBOUND, UserRole.WAREHOUSE},
            "grouping": "container + warehouse + unload date; limited to your access scope"}


def save_shipment(db, user, anchor_id, payload):
    rows = shipment_rows(db, user, anchor_id, lock=True)
    current = (rows[0].source_metadata or {}).get('ocean_shipment', {})
    if current.get('version', 0) != payload.version:
        raise HTTPException(409, 'Shipment changed. Refresh before saving.')
    # Inline list edits must not reset unrelated shipment metadata to schema defaults.
    values = {**current, **payload.model_dump(mode='json', exclude_unset=True), 'version': payload.version+1}
    for row in rows:
        require_live_record(db, row)
        row.source_metadata = {**(row.source_metadata or {}), 'ocean_shipment': values}
    db.add(AuditLog(user_id=user.id, action='OCEAN_SHIPMENT', entity_type='INBOUND', entity_id=rows[0].id, before_data=current, after_data=values))
    db.commit()
    db.expire_all()
    return read_shipment(db, user, anchor_id)


def save_receipts(db, user, anchor_id, payload, *, confirm=False):
    rows = {r.id: r for r in shipment_rows(db, user, anchor_id, lock=True)}
    if len({line.id for line in payload.lines}) != len(payload.lines):
        raise HTTPException(422, "Duplicate receipt lines")
    # Validate the entire batch before changing any row.
    for line in payload.lines:
        row = rows.get(line.id)
        if row is None:
            raise HTTPException(404, "Receipt line is outside this shipment or your access scope")
        require_live_record(db, row)
        receipt = (row.source_metadata or {}).get(KEY) or {}
        if receipt.get("version", 0) != line.version:
            raise HTTPException(409, "Receipt changed. Reload before saving.")
        if row.status not in (0, 1) or row.inventory_lot is not None:
            raise HTTPException(409, "Only pending or unloading cargo without inventory can be received")
        if line.location_id is not None:
            location = db.get(WarehouseLocation, line.location_id)
            if location is None or not location.is_active or location.warehouse_id != row.warehouse_id:
                raise HTTPException(422, "Location does not belong to this warehouse")
        if confirm and (line.received_qty is None or line.inbound_pallets is None or line.location_id is None):
            raise HTTPException(422, "Enter received cartons, inbound pallets and location for every selected line")
        if confirm and line.received_qty != row.carton_qty and not line.memo.strip():
            raise HTTPException(422, "Explain the carton discrepancy in Memo before confirming")
    for line in payload.lines:
        row = rows[line.id]
        metadata = dict(row.source_metadata or {})
        before = dict(metadata.get(KEY) or {})
        receipt = {**before, **line.model_dump(mode="json", exclude={"id"}), "version": line.version + 1,
                   "expected_qty": before.get("expected_qty", str(row.carton_qty)),
                   "expected_pallets": before.get("expected_pallets", str(row.pallet_qty))}
        if confirm:
            receipt.update(confirmed_by=user.id, confirmed_date=get_business_today().isoformat())
            row.carton_qty = line.received_qty
            row.pallet_qty = line.inbound_pallets
            row.location_id = line.location_id
            row.received_date = get_business_today()
            row.status = 2
        metadata[KEY] = receipt
        row.source_metadata = metadata
        db.add(AuditLog(user_id=user.id, action="OCEAN_RECEIVE" if confirm else "OCEAN_DRAFT",
                        entity_type="INBOUND", entity_id=row.id, before_data=jsonable_encoder(before), after_data=receipt))
    db.commit()
    db.expire_all()
    return read_shipment(db, user, anchor_id)


def putaway(db, user, anchor_id, payload):
    from app.services.inventory import receive_inbound
    rows = {r.id: r for r in shipment_rows(db, user, anchor_id, lock=True)}
    if len({x.id for x in payload.lines}) != len(payload.lines):
        raise HTTPException(422, 'Duplicate receipt lines')
    for line in payload.lines:
        row = rows.get(line.id)
        if not row:
            raise HTTPException(404, 'Receipt line is outside this shipment or access scope')
        require_live_record(db, row)
        if ((row.source_metadata or {}).get(KEY) or {}).get('version', 0) != line.version:
            raise HTTPException(409, 'Receipt changed. Reload before put away.')
        if row.status != 2 or row.inventory_lot is not None:
            raise HTTPException(409, 'Only received cargo without inventory can be put away')
        location = db.get(WarehouseLocation, row.location_id) if row.location_id else None
        if not location or not location.is_active or location.warehouse_id != row.warehouse_id:
            raise HTTPException(422, 'An active warehouse location is required')
        if row.carton_qty <= 0 or row.pallet_qty <= 0:
            raise HTTPException(422, 'Put away requires positive received cartons and pallets')
    for line in payload.lines:
        row = rows[line.id]
        row.status = 3
        row.source_metadata = {**(row.source_metadata or {}), KEY: {
            **((row.source_metadata or {}).get(KEY) or {}), 'version': line.version+1}}
        db.flush()
        receive_inbound(db, row.id, user.id, commit=False)
        db.add(AuditLog(user_id=user.id, action='OCEAN_PUTAWAY', entity_type='INBOUND', entity_id=row.id,
                        after_data={'status': 3, 'version': line.version+1}))
    db.commit()
    db.expire_all()
    return read_shipment(db, user, anchor_id)
