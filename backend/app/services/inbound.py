from datetime import date
from decimal import Decimal
from math import ceil

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    AuditLog,
    Customer,
    InboundLine,
    InboundRecord,
    User,
    Warehouse,
    WarehouseLocation,
)
from app.schemas.inbound import (
    InboundCreate,
    InboundLineInput,
    InboundLineRead,
    InboundListParams,
    InboundListResponse,
    InboundPatch,
    InboundRead,
    InboundUpdate,
    NamedRef,
    PaginationMeta,
    UserRef,
)
from app.services.access_policy import customer_clause, warehouse_clause
from app.utils.business_time import get_business_today

ZERO = Decimal("0")
SORTABLE = {
    "id": InboundRecord.id,
    "inbound_no": InboundRecord.inbound_no,
    "container_number": InboundRecord.container_number,
    "unload_date": InboundRecord.unload_date,
    "received_date": InboundRecord.received_date,
    "fc_code": InboundRecord.fc_code,
    "pallet_qty": InboundRecord.pallet_qty,
    "created_at": InboundRecord.created_at,
}


def _line_from_flat(payload) -> InboundLineInput:
    return InboundLineInput(
        line_no=1,
        fc_code=payload.fc_code,
        pallet_qty=payload.pallet_qty or ZERO,
        carton_qty=payload.carton_qty or ZERO,
        weight_lbs=payload.weight_lbs,
        cbm=payload.cbm,
        location_id=payload.location_id,
        remark=payload.remark,
    )


def _validate_refs(
    db: Session, *, warehouse_id: int, customer_id: int | None, location_ids: list[int | None]
) -> None:
    if db.get(Warehouse, warehouse_id) is None:
        raise HTTPException(422, "Warehouse not found")
    if customer_id and db.get(Customer, customer_id) is None:
        raise HTTPException(422, "Customer not found")
    for location_id in {item for item in location_ids if item is not None}:
        location = db.get(WarehouseLocation, location_id)
        if location is None or location.warehouse_id != warehouse_id:
            raise HTTPException(422, "Location does not belong to warehouse")


def _sync_header(record: InboundRecord) -> None:
    lines = list(record.lines)
    record.pallet_qty = sum((line.pallet_qty or ZERO for line in lines), ZERO)
    record.carton_qty = sum((line.carton_qty or ZERO for line in lines), ZERO)
    record.weight_lbs = sum((line.weight_lbs or ZERO for line in lines), ZERO)
    record.cbm = sum((line.cbm or ZERO for line in lines), ZERO)
    if len(lines) == 1:
        record.fc_code = lines[0].fc_code
        record.location_id = lines[0].location_id


def generate_inbound_no(db: Session, today: date | None = None) -> str:
    day = today or get_business_today()
    prefix = f"IB{day:%y%m%d}"
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": prefix}
        )
    last = db.scalar(
        select(func.max(InboundRecord.inbound_no)).where(
            InboundRecord.inbound_no.like(f"{prefix}%")
        )
    )
    return f"{prefix}{(int(last[-4:]) + 1 if last else 1):04d}"


def _named(obj, kind: str) -> NamedRef | None:
    if obj is None:
        return None
    return NamedRef(
        id=obj.id,
        code=getattr(obj, f"{kind}_code"),
        name=getattr(obj, f"{kind}_name"),
    )


def _read(row: InboundRecord) -> InboundRead:
    lots = sorted(row.inventory_lots, key=lambda lot: lot.id)
    lines = [
        InboundLineRead(
            id=line.id,
            line_no=line.line_no,
            fc_code=line.fc_code,
            pallet_qty=line.pallet_qty,
            carton_qty=line.carton_qty,
            weight_lbs=line.weight_lbs,
            cbm=line.cbm,
            location_id=line.location_id,
            location=_named(line.location, "location"),
            remark=line.remark,
            inventory_lot_id=line.inventory_lot.id if line.inventory_lot else None,
        )
        for line in row.lines
    ]
    return InboundRead.model_validate(
        {
            **row.__dict__,
            "customer": _named(row.customer, "customer"),
            "warehouse": _named(row.warehouse, "warehouse"),
            "location": _named(row.location, "location"),
            "created_by": UserRef(
                id=row.creator.id, display_name=row.creator.display_name
            ),
            "lines": lines,
            "inventory_created": bool(lots),
            "inventory_lot_id": lots[0].id if lots else None,
            "inventory_lot_ids": [lot.id for lot in lots],
        }
    )


def create_inbound(
    db: Session,
    payload: InboundCreate,
    user_id: int,
    import_job_id: int | None = None,
    commit: bool = True,
) -> InboundRecord:
    lines = payload.lines or [_line_from_flat(payload)]
    _validate_refs(
        db,
        warehouse_id=payload.warehouse_id,
        customer_id=payload.customer_id,
        location_ids=[line.location_id for line in lines] + [payload.location_id],
    )
    values = payload.model_dump(mode="python", exclude={"lines"})
    record = InboundRecord(
        **values,
        inbound_no=generate_inbound_no(db),
        created_by=user_id,
        import_job_id=import_job_id,
    )
    record.lines = [InboundLine(**line.model_dump(mode="python")) for line in lines]
    _sync_header(record)
    db.add(record)
    db.flush()
    db.add(
        AuditLog(
            user_id=user_id,
            action="CREATE",
            entity_type="INBOUND",
            entity_id=record.id,
            after_data=jsonable_encoder(payload),
        )
    )
    if commit:
        db.commit()
        db.refresh(record)
    return record


def _load_options():
    return (
        joinedload(InboundRecord.customer),
        joinedload(InboundRecord.warehouse),
        joinedload(InboundRecord.location),
        joinedload(InboundRecord.creator),
        selectinload(InboundRecord.inventory_lots),
        selectinload(InboundRecord.lines).joinedload(InboundLine.location),
        selectinload(InboundRecord.lines).joinedload(InboundLine.inventory_lot),
    )


def get_inbound(
    db: Session, record_id: int, user: User | None = None
) -> InboundRecord:
    filters = [InboundRecord.id == record_id]
    if user:
        filters.extend(
            clause
            for clause in (
                warehouse_clause(user, InboundRecord.warehouse_id),
                customer_clause(user, InboundRecord.customer_id),
            )
            if clause is not None
        )
    row = db.scalar(
        select(InboundRecord)
        .options(*_load_options())
        .where(*filters)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise HTTPException(404, "Inbound record not found")
    return row


def list_inbounds(
    db: Session, params: InboundListParams, user: User | None = None
) -> InboundListResponse:
    filters = []
    if user:
        filters.extend(
            clause
            for clause in (
                warehouse_clause(user, InboundRecord.warehouse_id),
                customer_clause(user, InboundRecord.customer_id),
            )
            if clause is not None
        )
    if params.q:
        term = f"%{params.q}%"
        filters.append(
            or_(
                InboundRecord.inbound_no.ilike(term),
                InboundRecord.container_number.ilike(term),
                InboundRecord.po_number.ilike(term),
                InboundRecord.fc_code.ilike(term),
                InboundRecord.marking.ilike(term),
                InboundRecord.remark.ilike(term),
            )
        )
    for value, column in (
        (params.container_number, InboundRecord.container_number),
        (params.customer_id, InboundRecord.customer_id),
        (params.warehouse_id, InboundRecord.warehouse_id),
        (params.status, InboundRecord.status),
    ):
        if value is not None:
            filters.append(
                column.ilike(f"%{value}%") if isinstance(value, str) else column == value
            )
    if params.fc_code is not None:
        filters.append(
            or_(
                InboundRecord.fc_code.ilike(f"%{params.fc_code}%"),
                InboundRecord.lines.any(InboundLine.fc_code.ilike(f"%{params.fc_code}%")),
            )
        )
    if params.location_id is not None:
        filters.append(
            or_(
                InboundRecord.location_id == params.location_id,
                InboundRecord.lines.any(InboundLine.location_id == params.location_id),
            )
        )
    for value, column, operator in (
        (params.unload_date_from, InboundRecord.unload_date, "ge"),
        (params.unload_date_to, InboundRecord.unload_date, "le"),
        (params.received_date_from, InboundRecord.received_date, "ge"),
        (params.received_date_to, InboundRecord.received_date, "le"),
    ):
        if value:
            filters.append(column >= value if operator == "ge" else column <= value)
    total = db.scalar(select(func.count()).select_from(InboundRecord).where(*filters)) or 0
    sort = SORTABLE.get(params.sort_by, InboundRecord.id)
    order = sort.asc() if params.sort_order == "asc" else sort.desc()
    rows = db.scalars(
        select(InboundRecord)
        .options(*_load_options())
        .where(*filters)
        .order_by(order)
        .offset((params.page - 1) * params.per_page)
        .limit(params.per_page)
    ).all()
    return InboundListResponse(
        data=[_read(row) for row in rows],
        meta=PaginationMeta(
            page=params.page,
            per_page=params.per_page,
            total=total,
            total_pages=ceil(total / params.per_page) if total else 0,
        ),
    )


def update_inbound(
    db: Session,
    row: InboundRecord,
    payload: InboundUpdate | InboundPatch,
    user_id: int,
    *,
    require_draft: bool = False,
) -> InboundRecord:
    if require_draft and row.status != 0:
        raise HTTPException(409, "Only draft inbound records can be edited")
    changes = payload.model_dump(mode="python", exclude_unset=True)
    supplied_lines = changes.pop("lines", None)
    replaces_lines = supplied_lines is not None
    warehouse_id = changes.get("warehouse_id", row.warehouse_id)
    customer_id = changes.get("customer_id", row.customer_id)
    if replaces_lines:
        lines = [InboundLineInput.model_validate(line) for line in supplied_lines]
    else:
        lines = None
    location_ids = [changes.get("location_id", row.location_id)]
    if lines is not None:
        location_ids.extend(line.location_id for line in lines)
    else:
        location_ids.extend(line.location_id for line in row.lines)
    _validate_refs(
        db,
        warehouse_id=warehouse_id,
        customer_id=customer_id,
        location_ids=location_ids,
    )
    before = jsonable_encoder(_read(row))
    for key, value in changes.items():
        setattr(row, key, value)
    if replaces_lines:
        if row.inventory_lots:
            raise HTTPException(409, "Inbound lines cannot change after inventory creation")
        for old_line in list(row.lines):
            db.delete(old_line)
        db.flush()
        row.lines = [InboundLine(**line.model_dump(mode="python")) for line in lines]
    elif isinstance(payload, InboundUpdate) and len(row.lines) == 1:
        legacy_line = _line_from_flat(payload)
        line = row.lines[0]
        for key in (
            "fc_code",
            "pallet_qty",
            "carton_qty",
            "weight_lbs",
            "cbm",
            "location_id",
            "remark",
        ):
            setattr(line, key, getattr(legacy_line, key))
    elif len(row.lines) == 1:
        # A partial legacy patch keeps the synthesized line in sync with the
        # retained flat fields.
        line = row.lines[0]
        for key in (
            "fc_code",
            "pallet_qty",
            "carton_qty",
            "weight_lbs",
            "cbm",
            "location_id",
            "remark",
        ):
            if key in changes:
                setattr(line, key, changes[key])
    _sync_header(row)
    db.add(
        AuditLog(
            user_id=user_id,
            action="UPDATE",
            entity_type="INBOUND",
            entity_id=row.id,
            before_data=before,
            after_data=jsonable_encoder(payload),
        )
    )
    db.commit()
    return get_inbound(db, row.id)


def delete_inbound(db: Session, row: InboundRecord, user_id: int) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action="DELETE",
            entity_type="INBOUND",
            entity_id=row.id,
            before_data=jsonable_encoder(
                {
                    "inbound_no": row.inbound_no,
                    "container_number": row.container_number,
                }
            ),
        )
    )
    db.delete(row)
    db.commit()
