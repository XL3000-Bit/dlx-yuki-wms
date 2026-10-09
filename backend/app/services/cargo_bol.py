"""Cargo BOL identities and transactional allocation of their remaining stock."""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import (
    CargoBOL, Customer, FBAInventoryAllocation, FBAShipment, ImportJob,
    InboundRecord, InventoryLot, OutboundInventoryAllocation, OutboundOrder, Warehouse,
)
from app.schemas.outbound import AllocateRequest
from app.services.access_policy import scoped_statement
from app.services.history_policy import require_live_record

HISTORY_PROFILE = "WEST_COAST_4_0_HISTORY"
QUANTITIES = ("pallet_qty", "carton_qty", "weight_lbs", "cbm")
ZERO = Decimal("0")


def backfill_cargo_bols(db: Session):
    """Idempotent identity-only migration. Never receive or adjust inventory."""
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    for model, key in ((InboundRecord, "inbound_id"), (FBAShipment, "fba_shipment_id"),
                       (OutboundOrder, "history_outbound_id")):
        query = select(model.id)
        if model is OutboundOrder:
            query = query.join(ImportJob, model.import_job_id == ImportJob.id).where(
                ImportJob.profile_code == HISTORY_PROFILE)
        query = query.where(~exists(select(CargoBOL.id).where(getattr(CargoBOL, key) == model.id)))
        db.execute(insert(CargoBOL).from_select([key], query.order_by(model.id)).on_conflict_do_nothing())
    fba_source = select(FBAInventoryAllocation.fba_shipment_id).where(
        FBAInventoryAllocation.id == OutboundInventoryAllocation.fba_allocation_id).correlate(
        OutboundInventoryAllocation).scalar_subquery()
    inbound_source = select(InventoryLot.source_inbound_id).where(
        InventoryLot.id == OutboundInventoryAllocation.inventory_lot_id).correlate(
        OutboundInventoryAllocation).scalar_subquery()
    identity = select(CargoBOL.id).where(or_(
        and_(OutboundInventoryAllocation.fba_allocation_id.is_not(None), CargoBOL.fba_shipment_id == fba_source),
        and_(OutboundInventoryAllocation.fba_allocation_id.is_(None), CargoBOL.inbound_id == inbound_source),
    )).correlate(OutboundInventoryAllocation).scalar_subquery()
    db.execute(update(OutboundInventoryAllocation).where(
        OutboundInventoryAllocation.cargo_bol_id.is_(None)).values(cargo_bol_id=identity))
    db.flush()


def identity_for_allocation(db, lot, fba=None):
    key = CargoBOL.fba_shipment_id == fba.fba_shipment_id if fba else CargoBOL.inbound_id == lot.source_inbound_id
    identity = db.scalar(select(CargoBOL).where(key))
    if not identity:
        raise HTTPException(409, "货物尚未生成 BOL 编号，请先补齐货物编号")
    return identity


def document_identity(allocation):
    identity = allocation.cargo_bol
    return {"cargo_bol_no": identity.bol_no if identity else None,
            "po_number": getattr(identity.source, "po_number", None) if identity else None}


def _statement(user):
    # FBA reservations have already left available inventory; subtract only the
    # uncompleted outbound reservations, since completion reduces the FBA balance.
    used = select(OutboundInventoryAllocation.fba_allocation_id.label("id"), *[
        func.sum(getattr(OutboundInventoryAllocation, "allocated_" + q) -
                 getattr(OutboundInventoryAllocation, "completed_" + q)).label(q)
        for q in QUANTITIES
    ]).group_by(OutboundInventoryAllocation.fba_allocation_id).subquery()
    fba_remaining = select(FBAInventoryAllocation.fba_shipment_id.label("id"), *[
        func.sum(getattr(FBAInventoryAllocation, "allocated_" + q) - func.coalesce(used.c[q], 0)).label(q)
        for q in QUANTITIES
    ]).outerjoin(used, used.c.id == FBAInventoryAllocation.id).group_by(
        FBAInventoryAllocation.fba_shipment_id).subquery()
    warehouse_id = func.coalesce(InboundRecord.warehouse_id, FBAShipment.warehouse_id, OutboundOrder.warehouse_id)
    customer_id = func.coalesce(InboundRecord.customer_id, FBAShipment.customer_id, OutboundOrder.customer_id)
    source_job = func.coalesce(InboundRecord.import_job_id, FBAShipment.import_job_id, OutboundOrder.import_job_id)
    historical = exists(select(ImportJob.id).where(ImportJob.id == source_job, ImportJob.profile_code == HISTORY_PROFILE))
    available = {q: func.coalesce(InventoryLot.__table__.c["available_" + q], fba_remaining.c[q], 0)
                 for q in QUANTITIES}
    query = select(
        CargoBOL.id, CargoBOL.inbound_id, CargoBOL.fba_shipment_id, CargoBOL.history_outbound_id,
        func.coalesce(InboundRecord.inbound_no, FBAShipment.fba_no, OutboundOrder.ob_no).label("source_no"),
        func.coalesce(InboundRecord.po_number, FBAShipment.po_number, OutboundOrder.po_number).label("po_number"),
        InboundRecord.container_number, warehouse_id.label("warehouse_id"), customer_id.label("customer_id"),
        Warehouse.warehouse_name.label("warehouse_name"), Customer.customer_name.label("customer_name"),
        func.coalesce(InboundRecord.fc_code, FBAShipment.amazon_fc_code, OutboundOrder.del_code, OutboundOrder.fc_code).label("del_code"),
        InventoryLot.lot_no, InventoryLot.id.label("inventory_lot_id"),
        InboundRecord.received_date.label("actual_inbound_date"),
        FBAShipment.appointment_time.label("appointment_time"),
        OutboundOrder.redirect_code, OutboundOrder.transfer_code,
        historical.label("historical"), CargoBOL.created_at,
        *[value.label("available_" + q) for q, value in available.items()],
    ).select_from(CargoBOL).outerjoin(InboundRecord, CargoBOL.inbound_id == InboundRecord.id).outerjoin(
        FBAShipment, CargoBOL.fba_shipment_id == FBAShipment.id).outerjoin(
        OutboundOrder, CargoBOL.history_outbound_id == OutboundOrder.id).outerjoin(
        InventoryLot, InventoryLot.source_inbound_id == InboundRecord.id).outerjoin(
        fba_remaining, fba_remaining.c.id == FBAShipment.id).outerjoin(
        Warehouse, Warehouse.id == warehouse_id).outerjoin(Customer, Customer.id == customer_id)
    return scoped_statement(query, user, warehouse_column=warehouse_id, customer_column=customer_id), historical, available


def _serialize(row):
    data = dict(row)
    data["bol_no"] = f"BOL{data['id']:012d}"
    data["source_type"] = "INBOUND" if data["inbound_id"] else "FBA" if data["fba_shipment_id"] else "HISTORY_OUTBOUND"
    data["can_allocate"] = not data["historical"] and any(data["available_" + q] > 0 for q in QUANTITIES[:2])
    data["status_name"] = "历史记录 · 库存待核对" if data["historical"] else "可配货" if data["can_allocate"] else "暂无可配库存"
    return data


def _filtered_statement(user, q="", remaining_only=False, warehouse_id=None,
                        customer_id=None, source_type=None, del_code=None):
    statement, historical, available = _statement(user)
    if q.strip():
        term = q.strip()
        # Escape SQL wildcard characters: PO identifiers may contain underscores.
        pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        conditions = [column.ilike(pattern, escape="\\") for column in (
            InboundRecord.po_number, FBAShipment.po_number, OutboundOrder.po_number,
            InboundRecord.container_number, InboundRecord.inbound_no, FBAShipment.fba_no, OutboundOrder.ob_no)]
        number = term.upper().removeprefix("BOL")
        if number.isdigit() and len(number) <= 18:
            conditions.append(CargoBOL.id == int(number))
        statement = statement.where(or_(*conditions))
    if remaining_only:
        statement = statement.where(~historical, or_(*(available[q] > 0 for q in QUANTITIES[:2])))
    columns = statement.selected_columns
    if warehouse_id is not None:
        statement = statement.where(columns.warehouse_id == warehouse_id)
    if customer_id is not None:
        statement = statement.where(columns.customer_id == customer_id)
    if source_type:
        source = {"INBOUND": CargoBOL.inbound_id, "FBA": CargoBOL.fba_shipment_id,
                  "HISTORY_OUTBOUND": CargoBOL.history_outbound_id}[source_type]
        statement = statement.where(source.is_not(None))
    if del_code and del_code.strip():
        statement = statement.where(func.upper(columns.del_code) == del_code.strip().upper())
    return statement


def list_cargo_bols(db, user, q="", remaining_only=False, page=1, page_size=20, **filters):
    statement = _filtered_statement(user, q, remaining_only, **filters)
    filtered = statement.subquery()
    aggregate = db.execute(select(func.count().label("total"), *[
        func.coalesce(func.sum(filtered.c["available_" + q]), 0).label("available_" + q)
        for q in QUANTITIES
    ]).select_from(filtered)).mappings().one()
    rows = db.execute(statement.order_by(CargoBOL.id.desc()).offset((page - 1) * page_size).limit(page_size)).mappings()
    return {"data": [_serialize(row) for row in rows], "meta": {
        "total": aggregate["total"], "page": page, "page_size": page_size,
        "totals": {"available_" + q: aggregate["available_" + q] for q in QUANTITIES}}}


def export_cargo_bols(db, user, **filters):
    from io import BytesIO
    from openpyxl import Workbook

    statement = _filtered_statement(user, **filters)
    # Bound exports and report the limit instead of silently truncating results.
    rows = db.execute(statement.order_by(CargoBOL.id.desc()).limit(10001)).mappings().all()
    if len(rows) > 10000:
        raise HTTPException(422, "导出最多 10000 条，请缩小筛选范围")
    fields = [("BOL#", "bol_no"), ("Source", "source_type"), ("Source#", "source_no"),
              ("PO#", "po_number"), ("CNTR#", "container_number"), ("Warehouse", "warehouse_name"),
              ("Customer", "customer_name"), ("Del Code", "del_code"), ("Status", "status_name"),
              ("Remaining PLT", "available_pallet_qty"), ("Remaining CTN", "available_carton_qty"),
              ("Remaining LB", "available_weight_lbs"), ("Remaining CBM", "available_cbm")]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Cargo BOL"
    sheet.append([title for title, _ in fields])
    for record in rows:
        data = _serialize(record)
        sheet.append([data.get(key) for _, key in fields])
        # Imported references must remain text, including strings beginning '='.
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    result = BytesIO()
    workbook.save(result)
    return result.getvalue()


def cargo_detail(db, user, identity_id):
    statement, _, _ = _statement(user)
    row = db.execute(statement.where(CargoBOL.id == identity_id)).mappings().first()
    if not row:
        raise HTTPException(404, "BOL 不存在或无权访问")
    result = _serialize(row)
    allocations = select(OutboundInventoryAllocation, OutboundOrder).join(
        OutboundOrder, OutboundOrder.id == OutboundInventoryAllocation.outbound_order_id).where(
        OutboundInventoryAllocation.cargo_bol_id == identity_id)
    allocations = scoped_statement(allocations, user, warehouse_column=OutboundOrder.warehouse_id,
                                   customer_column=OutboundOrder.customer_id)
    result["outbounds"] = [{"id": ob.id, "allocation_id": a.id, "ob_no": ob.ob_no,
        **{"allocated_" + q: getattr(a, "allocated_" + q) for q in QUANTITIES},
        **{"completed_" + q: getattr(a, "completed_" + q) for q in QUANTITIES}}
        for a, ob in db.execute(allocations)]
    return result


def assign_remaining(db, user, ob_id, identity_ids):
    from app.services.outbound import allocate, get_ob
    try:
        ob = get_ob(db, ob_id, lock=True, user=user)
        identities = []
        for identity_id in sorted(set(identity_ids)):
            info = cargo_detail(db, user, identity_id)
            if info["historical"]:
                raise HTTPException(409, "历史货物尚未核对库存，不能配入 OB")
            if info["warehouse_id"] != ob.warehouse_id or info["customer_id"] != ob.customer_id:
                raise HTTPException(409, "BOL 与 OB 的仓库、客户必须一致")
            identities.append(db.get(CargoBOL, identity_id))
        sources = []
        for identity in identities:
            require_live_record(db, identity.source)
            if identity.fba_shipment_id:
                if ob.ob_type != "FBA" or ob.fba_shipment_id != identity.fba_shipment_id:
                    raise HTTPException(409, "FBA BOL 只能配入关联同一 FBA 货件的 OB")
                for reservation in db.scalars(select(FBAInventoryAllocation).where(
                        FBAInventoryAllocation.fba_shipment_id == identity.fba_shipment_id)):
                    sources.append((reservation.inventory_lot_id, reservation.id))
            else:
                if ob.ob_type == "FBA":
                    raise HTTPException(409, "FBA OB 请从对应的 FBA BOL 配货")
                lot_id = db.scalar(select(InventoryLot.id).where(InventoryLot.source_inbound_id == identity.inbound_id))
                if not lot_id:
                    raise HTTPException(409, "所选 BOL 尚未入库，没有可配库存")
                sources.append((lot_id, None))
        # Match allocate()'s lot-before-FBA lock order. Read quantities after locks.
        lots = {lot.id: lot for lot in db.scalars(select(InventoryLot).where(
            InventoryLot.id.in_([item[0] for item in sources])).order_by(InventoryLot.id).with_for_update()
            .execution_options(populate_existing=True))}
        reservations = {a.id: a for a in db.scalars(select(FBAInventoryAllocation).where(
            FBAInventoryAllocation.id.in_([item[1] for item in sources if item[1]])).order_by(
                FBAInventoryAllocation.id).with_for_update().execution_options(populate_existing=True))}
        allocated = []
        assigned_bols = set()
        for lot_id, reservation_id in sorted(sources, key=lambda item: (item[0], item[1] or 0)):
            if reservation_id:
                reservation = reservations[reservation_id]
                used = db.execute(select(*[func.coalesce(func.sum(
                    getattr(OutboundInventoryAllocation, "allocated_" + q) -
                    getattr(OutboundInventoryAllocation, "completed_" + q)), 0) for q in QUANTITIES]).where(
                        OutboundInventoryAllocation.fba_allocation_id == reservation_id)).one()
                quantities = {q: getattr(reservation, "allocated_" + q) - used[i] for i, q in enumerate(QUANTITIES)}
            else:
                quantities = {q: getattr(lots[lot_id], "available_" + q) for q in QUANTITIES}
            if not any(quantities[q] > 0 for q in QUANTITIES[:2]):
                continue
            if any(value < 0 for value in quantities.values()):
                raise HTTPException(409, "库存数量异常，请先核对")
            allocation = allocate(db, ob.id, AllocateRequest(inventory_lot_id=lot_id,
                fba_allocation_id=reservation_id, **quantities), user.id, commit=False)
            allocated.append(allocation.id)
            assigned_bols.add(allocation.cargo_bol_id)
        if assigned_bols != set(identity_ids):
            raise HTTPException(409, "部分 BOL 已无可配库存；本次未配入任何货物，请刷新后重选")
        db.commit()
        return {"ob_id": ob.id, "ob_no": ob.ob_no, "bol_count": len(assigned_bols), "allocation_ids": allocated}
    except Exception:
        db.rollback()
        raise
