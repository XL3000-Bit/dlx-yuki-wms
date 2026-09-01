from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    FBAShipment,
    InventoryLot,
    Load,
    OutboundInventoryAllocation,
    OutboundOrder,
    PickQuantityUnit,
    PickingList,
    PickingListItem,
    PickingStatus,
    ScanEvent,
    ScanEventType,
    ScanOperationType,
    ScanResult,
    ScanSession,
    ScanSessionStatus,
    ScanType,
    User,
    UserRole,
    Warehouse,
    WarehouseLocation,
)
from app.models.inventory import InventoryStatus
from app.schemas.scan_execution import (
    PickConfirmationRequest,
    PickingExecutionSummary,
    ScanCounters,
    ScanSessionCreate,
)
from app.services.access_policy import (
    assert_customer_access,
    assert_warehouse_access,
    customer_clause,
    warehouse_clause,
)
from app.utils.business_time import get_business_today


ZERO = Decimal("0")
PICKING_STATUS_LABELS = {
    PickingStatus.NEW: "NOT_STARTED",
    PickingStatus.PRINTED: "NOT_STARTED",
    PickingStatus.IN_PROGRESS: "IN_PROGRESS",
    PickingStatus.COMPLETED: "COMPLETED",
    PickingStatus.CANCELED: "CANCELED",
    PickingStatus.EXCEPTION: "EXCEPTION",
}
PICKABLE_INVENTORY_STATUSES = {
    InventoryStatus.AVAILABLE,
    InventoryStatus.PARTIALLY_ALLOCATED,
    InventoryStatus.FULLY_ALLOCATED,
}


@dataclass(frozen=True)
class ResolvedScan:
    scan_type: ScanType
    result: ScanResult
    message: str
    matched_entity_type: str | None = None
    matched_entity_id: int | None = None
    location_id: int | None = None
    reference_value: str | None = None


def normalize_scan_value(value: str) -> str:
    """Normalize scanner framing without changing meaningful identifier content."""
    return value.replace("\r", "").replace("\n", "").strip()


def _scoped_session(db: Session, session_id: int, user: User) -> ScanSession:
    stmt = select(ScanSession).where(ScanSession.id == session_id)
    warehouse_scope = warehouse_clause(user, ScanSession.warehouse_id)
    if warehouse_scope is not None:
        stmt = stmt.where(warehouse_scope)
    session = db.scalar(stmt)
    if session is None or (user.role != UserRole.ADMIN and session.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan session not found")
    return session


def get_scan_session(db: Session, session_id: int, user: User) -> ScanSession:
    return _scoped_session(db, session_id, user)


def _scoped_outbound(db: Session, outbound_id: int, user: User) -> OutboundOrder:
    stmt = select(OutboundOrder).where(OutboundOrder.id == outbound_id)
    for clause in (
        warehouse_clause(user, OutboundOrder.warehouse_id),
        customer_clause(user, OutboundOrder.customer_id),
    ):
        if clause is not None:
            stmt = stmt.where(clause)
    outbound = db.scalar(stmt)
    if outbound is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outbound order not found")
    return outbound


def _scoped_picking(db: Session, picking_id: int, user: User) -> PickingList:
    stmt = (
        select(PickingList)
        .join(OutboundOrder, OutboundOrder.id == PickingList.outbound_order_id)
        .where(PickingList.id == picking_id)
    )
    for clause in (
        warehouse_clause(user, OutboundOrder.warehouse_id),
        customer_clause(user, OutboundOrder.customer_id),
    ):
        if clause is not None:
            stmt = stmt.where(clause)
    picking = db.scalar(stmt)
    if picking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Picking list not found")
    return picking


def _scoped_picking_ref(db: Session, picking_ref: str, user: User) -> PickingList:
    normalized_ref = normalize_scan_value(picking_ref)
    stmt = (
        select(PickingList)
        .join(OutboundOrder, OutboundOrder.id == PickingList.outbound_order_id)
        .where(func.lower(PickingList.picking_no) == normalized_ref.lower())
    )
    for clause in (
        warehouse_clause(user, OutboundOrder.warehouse_id),
        customer_clause(user, OutboundOrder.customer_id),
    ):
        if clause is not None:
            stmt = stmt.where(clause)
    picking = db.scalar(stmt)
    if picking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Picking list not found")
    return picking


def _scoped_load(db: Session, load_id: int, user: User) -> Load:
    stmt = select(Load).where(Load.id == load_id)
    scope = warehouse_clause(user, Load.warehouse_id)
    if scope is not None:
        stmt = stmt.where(scope)
    load = db.scalar(stmt)
    if load is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Load not found")
    return load


def _generate_session_no(db: Session) -> str:
    prefix = f"SC-{get_business_today():%Y%m%d}-"
    for _attempt in range(50):
        candidate = f"{prefix}{secrets.randbelow(10_000):04d}"
        if db.scalar(select(ScanSession.id).where(ScanSession.session_no == candidate)) is None:
            return candidate
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Unable to allocate a unique scan session number",
    )


def create_scan_session(
    db: Session, payload: ScanSessionCreate, user: User
) -> ScanSession:
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Warehouse is invalid or inactive")
    assert_warehouse_access(user, payload.warehouse_id)

    outbound = _scoped_outbound(db, payload.outbound_id, user) if payload.outbound_id else None
    picking_by_id = _scoped_picking(db, payload.picking_id, user) if payload.picking_id else None
    picking_by_ref = (
        _scoped_picking_ref(db, payload.picking_ref, user) if payload.picking_ref else None
    )
    if (
        picking_by_id is not None
        and picking_by_ref is not None
        and picking_by_id.id != picking_by_ref.id
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Picking ID and picking reference identify different picking lists",
        )
    picking = picking_by_id or picking_by_ref
    load = _scoped_load(db, payload.load_id, user) if payload.load_id else None

    if payload.operation_type == ScanOperationType.PICK and picking is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "PICK scan sessions require a picking list",
        )
    if payload.operation_type == ScanOperationType.PICK and load is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "PICK scan sessions do not accept an independent load context",
        )

    if picking is not None:
        picking_outbound = _scoped_outbound(db, picking.outbound_order_id, user)
        if outbound is not None and picking_outbound.id != outbound.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Picking list does not belong to the selected outbound order",
            )
        outbound = outbound or picking_outbound
        if payload.operation_type == ScanOperationType.PICK and picking.status in {
            PickingStatus.COMPLETED,
            PickingStatus.CANCELED,
            PickingStatus.EXCEPTION,
        }:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Picking list is not open for scan execution",
            )

    for entity_name, entity in (("Outbound order", outbound), ("Load", load)):
        if entity is not None and entity.warehouse_id != payload.warehouse_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{entity_name} does not belong to the selected warehouse",
            )
    if outbound is not None:
        assert_customer_access(user, outbound.customer_id)
    if load is not None and outbound is not None and outbound.load_id != load.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Outbound order does not belong to the selected load",
        )

    if payload.operation_type == ScanOperationType.PICK:
        existing_open = db.scalar(
            select(ScanSession.id).where(
                ScanSession.operation_type == ScanOperationType.PICK.value,
                ScanSession.picking_id == picking.id,
                ScanSession.status == ScanSessionStatus.OPEN.value,
            )
        )
        if existing_open is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "An open PICK scan session already exists for this picking list",
            )

    session = ScanSession(
        session_no=_generate_session_no(db),
        warehouse_id=payload.warehouse_id,
        operation_type=payload.operation_type.value,
        user_id=user.id,
        outbound_id=outbound.id if outbound is not None else None,
        picking_id=picking.id if picking is not None else None,
        load_id=load.id if load is not None else None,
    )
    db.add(session)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if payload.operation_type == ScanOperationType.PICK:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "An open PICK scan session already exists for this picking list",
            ) from exc
        raise
    return session


def _apply_entity_scope(stmt, user: User, warehouse_column, customer_column=None):
    for clause in (
        warehouse_clause(user, warehouse_column),
        customer_clause(user, customer_column) if customer_column is not None else None,
    ):
        if clause is not None:
            stmt = stmt.where(clause)
    return stmt


def _location_allowed_for_picking(db: Session, picking_id: int, location_id: int) -> bool:
    return db.scalar(
        select(PickingListItem.id).where(
            PickingListItem.picking_list_id == picking_id,
            PickingListItem.location_id == location_id,
        ).limit(1)
    ) is not None


def _lot_allowed_for_context(db: Session, session: ScanSession, lot_id: int) -> bool:
    if session.picking_id is not None:
        return db.scalar(
            select(PickingListItem.id).where(
                PickingListItem.picking_list_id == session.picking_id,
                PickingListItem.inventory_lot_id == lot_id,
            ).limit(1)
        ) is not None
    if session.outbound_id is not None:
        return db.scalar(
            select(OutboundInventoryAllocation.id).where(
                OutboundInventoryAllocation.outbound_order_id == session.outbound_id,
                OutboundInventoryAllocation.inventory_lot_id == lot_id,
            ).limit(1)
        ) is not None
    return True


def _resolve_candidates(
    db: Session, session: ScanSession, user: User, normalized: str
) -> list[ResolvedScan]:
    # SQL lower() is the matching primitive used by the existing identifiers.
    # Keep the same normalization on the Python side instead of mixing it with
    # Unicode casefold semantics that PostgreSQL lower() does not guarantee.
    key = normalized.lower()
    accepted: list[ResolvedScan] = []
    mismatches: list[ResolvedScan] = []

    outbound_stmt = _apply_entity_scope(
        select(OutboundOrder).where(func.lower(OutboundOrder.ob_no) == key),
        user,
        OutboundOrder.warehouse_id,
        OutboundOrder.customer_id,
    )
    for row in db.scalars(outbound_stmt).all():
        result = ScanResult.ACCEPTED
        message = f"Outbound {row.ob_no} accepted"
        if row.warehouse_id != session.warehouse_id:
            result, message = ScanResult.WRONG_WAREHOUSE, "Outbound belongs to another warehouse"
        elif session.outbound_id is not None and row.id != session.outbound_id:
            result, message = ScanResult.WRONG_OUTBOUND, "Outbound does not match the session context"
        elif session.load_id is not None and row.load_id != session.load_id:
            result, message = ScanResult.WRONG_OUTBOUND, "Outbound does not belong to the session load"
        target = accepted if result == ScanResult.ACCEPTED else mismatches
        target.append(ResolvedScan(ScanType.OUTBOUND, result, message, "OutboundOrder", row.id, reference_value=row.ob_no))

    picking_stmt = _apply_entity_scope(
        select(PickingList)
        .join(OutboundOrder, OutboundOrder.id == PickingList.outbound_order_id)
        .where(func.lower(PickingList.picking_no) == key),
        user,
        OutboundOrder.warehouse_id,
        OutboundOrder.customer_id,
    )
    for row in db.scalars(picking_stmt).all():
        outbound = db.get(OutboundOrder, row.outbound_order_id)
        result = ScanResult.ACCEPTED
        message = f"Picking list {row.picking_no} accepted"
        if outbound is None or outbound.warehouse_id != session.warehouse_id:
            result, message = ScanResult.WRONG_WAREHOUSE, "Picking list belongs to another warehouse"
        elif session.picking_id is not None and row.id != session.picking_id:
            result, message = ScanResult.WRONG_OUTBOUND, "Picking list does not match the session context"
        elif session.outbound_id is not None and row.outbound_order_id != session.outbound_id:
            result, message = ScanResult.WRONG_OUTBOUND, "Picking list belongs to another outbound order"
        target = accepted if result == ScanResult.ACCEPTED else mismatches
        target.append(ResolvedScan(ScanType.PICKING, result, message, "PickingList", row.id, reference_value=row.picking_no))

    fba_stmt = _apply_entity_scope(
        select(FBAShipment).where(func.lower(FBAShipment.fba_no) == key),
        user,
        FBAShipment.warehouse_id,
        FBAShipment.customer_id,
    )
    for row in db.scalars(fba_stmt).all():
        result = ScanResult.ACCEPTED
        message = f"FBA shipment {row.fba_no} accepted"
        if row.warehouse_id != session.warehouse_id:
            result, message = ScanResult.WRONG_WAREHOUSE, "FBA shipment belongs to another warehouse"
        elif session.outbound_id is not None:
            outbound = db.get(OutboundOrder, session.outbound_id)
            if outbound is None or outbound.fba_shipment_id != row.id:
                result, message = ScanResult.WRONG_OUTBOUND, "FBA shipment does not match the session outbound"
        target = accepted if result == ScanResult.ACCEPTED else mismatches
        target.append(ResolvedScan(ScanType.FBA, result, message, "FBAShipment", row.id, reference_value=row.fba_no))

    location_stmt = _apply_entity_scope(
        select(WarehouseLocation).where(func.lower(WarehouseLocation.location_code) == key),
        user,
        WarehouseLocation.warehouse_id,
    )
    for row in db.scalars(location_stmt).all():
        result = ScanResult.ACCEPTED
        message = f"Location {row.location_code} accepted"
        if row.warehouse_id != session.warehouse_id:
            result, message = ScanResult.WRONG_WAREHOUSE, "Location belongs to another warehouse"
        elif session.picking_id is not None and not _location_allowed_for_picking(db, session.picking_id, row.id):
            result, message = ScanResult.WRONG_LOCATION, "Location is not used by the session picking list"
        target = accepted if result == ScanResult.ACCEPTED else mismatches
        target.append(ResolvedScan(ScanType.LOCATION, result, message, "WarehouseLocation", row.id, row.id, row.location_code))

    lot_stmt = _apply_entity_scope(
        select(InventoryLot).where(func.lower(InventoryLot.lot_no) == key),
        user,
        InventoryLot.warehouse_id,
        InventoryLot.customer_id,
    )
    for row in db.scalars(lot_stmt).all():
        result = ScanResult.ACCEPTED
        message = f"Inventory lot {row.lot_no} accepted"
        if row.warehouse_id != session.warehouse_id:
            result, message = ScanResult.WRONG_WAREHOUSE, "Inventory lot belongs to another warehouse"
        elif not _lot_allowed_for_context(db, session, row.id):
            result, message = ScanResult.WRONG_OUTBOUND, "Inventory lot is not allocated to the session context"
        target = accepted if result == ScanResult.ACCEPTED else mismatches
        target.append(ResolvedScan(ScanType.INVENTORY_LOT, result, message, "InventoryLot", row.id, row.location_id, row.lot_no))

    container_stmt = _apply_entity_scope(
        select(InventoryLot).where(func.lower(InventoryLot.container_number) == key),
        user,
        InventoryLot.warehouse_id,
        InventoryLot.customer_id,
    )
    container_rows = list(db.scalars(container_stmt).all())
    if container_rows:
        same_warehouse = [row for row in container_rows if row.warehouse_id == session.warehouse_id]
        context_rows = [row for row in same_warehouse if _lot_allowed_for_context(db, session, row.id)]
        reference = container_rows[0].container_number
        if not same_warehouse:
            mismatches.append(ResolvedScan(ScanType.CONTAINER, ScanResult.WRONG_WAREHOUSE, "Container belongs to another warehouse", "Container", reference_value=reference))
        elif not context_rows:
            mismatches.append(ResolvedScan(ScanType.CONTAINER, ScanResult.WRONG_OUTBOUND, "Container is not allocated to the session context", "Container", reference_value=reference))
        else:
            accepted.append(ResolvedScan(ScanType.CONTAINER, ScanResult.ACCEPTED, f"Container {reference} accepted", "Container", reference_value=reference))

    if len(accepted) == 1:
        return accepted
    if len(accepted) > 1:
        return [ResolvedScan(ScanType.UNKNOWN, ScanResult.REJECTED, "Scan value is ambiguous across supported identifier types")]
    if mismatches:
        priority = {
            ScanResult.WRONG_WAREHOUSE: 0,
            ScanResult.WRONG_OUTBOUND: 1,
            ScanResult.WRONG_LOCATION: 2,
        }
        return [min(mismatches, key=lambda item: priority.get(item.result, 99))]
    return [ResolvedScan(ScanType.UNKNOWN, ScanResult.NOT_FOUND, "No supported identifier matched the scan value")]


def _decimal(value: Decimal | int | None) -> Decimal:
    return Decimal(value or 0)


def _item_quantities(
    item: PickingListItem,
) -> tuple[PickQuantityUnit, Decimal, Decimal]:
    """Return the existing picking item's physical execution unit and progress."""
    if _decimal(item.planned_pallet_qty) > ZERO:
        return (
            PickQuantityUnit.PALLET,
            _decimal(item.planned_pallet_qty),
            _decimal(item.picked_pallet_qty),
        )
    return (
        PickQuantityUnit.CARTON,
        _decimal(item.planned_carton_qty),
        _decimal(item.picked_carton_qty),
    )


def _item_remaining(item: PickingListItem) -> Decimal:
    _unit, required, picked = _item_quantities(item)
    return max(required - picked, ZERO)


def _item_available(
    item: PickingListItem,
    allocation: OutboundInventoryAllocation,
    lot: InventoryLot,
) -> Decimal:
    unit, _required, _picked = _item_quantities(item)
    if unit == PickQuantityUnit.PALLET:
        allocation_remaining = max(
            _decimal(allocation.allocated_pallet_qty)
            - _decimal(allocation.completed_pallet_qty),
            ZERO,
        )
        lot_reserved = _decimal(lot.allocated_pallet_qty)
    else:
        allocation_remaining = max(
            _decimal(allocation.allocated_carton_qty)
            - _decimal(allocation.completed_carton_qty),
            ZERO,
        )
        lot_reserved = _decimal(lot.allocated_carton_qty)
    return min(_item_remaining(item), allocation_remaining, lot_reserved)


def _pick_step(session: ScanSession) -> str:
    if session.current_location_id is None:
        return "EXPECT_LOCATION"
    if session.current_picking_item_id is None:
        return "EXPECT_LOT"
    return "EXPECT_QUANTITY_CONFIRMATION"


def _new_scan_event(
    db: Session,
    session: ScanSession,
    user: User,
    *,
    raw_value: str,
    normalized_value: str,
    event_type: ScanEventType,
    scan_type: ScanType,
    result: ScanResult,
    message: str,
    matched_entity_type: str | None = None,
    matched_entity_id: int | None = None,
    location_id: int | None = None,
    picking_item_id: int | None = None,
    reference_value: str | None = None,
    client_operation_id: str | None = None,
    quantity: Decimal | None = None,
    quantity_unit: PickQuantityUnit | None = None,
) -> ScanEvent:
    event_row = ScanEvent(
        session_id=session.id,
        raw_value=raw_value,
        normalized_value=normalized_value,
        event_type=event_type.value,
        client_operation_id=client_operation_id,
        scan_type=scan_type.value,
        result=result.value,
        matched_entity_type=matched_entity_type,
        matched_entity_id=matched_entity_id,
        location_id=location_id,
        picking_item_id=picking_item_id,
        quantity=quantity,
        quantity_unit=quantity_unit.value if quantity_unit is not None else None,
        reference_value=reference_value,
        message=message,
        scanned_by=user.id,
    )
    db.add(event_row)
    session.last_scan_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(event_row)
    return event_row


def _pick_items(db: Session, picking_id: int) -> list[PickingListItem]:
    return list(
        db.scalars(
            select(PickingListItem)
            .where(PickingListItem.picking_list_id == picking_id)
            .order_by(PickingListItem.sequence_no, PickingListItem.id)
        ).all()
    )


def get_picking_execution_summary(
    db: Session, session: ScanSession
) -> PickingExecutionSummary | None:
    if session.operation_type != ScanOperationType.PICK.value or session.picking_id is None:
        return None
    picking = db.get(PickingList, session.picking_id)
    if picking is None:
        return None
    outbound = db.get(OutboundOrder, picking.outbound_order_id)
    items = _pick_items(db, picking.id)
    item_values = [_item_quantities(item) for item in items]
    units = {unit for unit, required, _picked in item_values if required > ZERO}
    quantity_unit = next(iter(units)).value if len(units) == 1 else ("MIXED" if units else None)
    required_qty = sum((required for _unit, required, _picked in item_values), ZERO)
    picked_qty = sum((min(picked, required) for _unit, required, picked in item_values), ZERO)

    current_location = (
        db.get(WarehouseLocation, session.current_location_id)
        if session.current_location_id is not None
        else None
    )
    current_item = (
        db.get(PickingListItem, session.current_picking_item_id)
        if session.current_picking_item_id is not None
        else None
    )
    current_lot = None
    current_values: tuple[PickQuantityUnit, Decimal, Decimal] | None = None
    current_available: Decimal | None = None
    if current_item is not None:
        current_lot = db.get(InventoryLot, current_item.inventory_lot_id)
        allocation = db.get(
            OutboundInventoryAllocation, current_item.outbound_allocation_id
        )
        current_values = _item_quantities(current_item)
        if current_lot is not None and allocation is not None:
            current_available = _item_available(current_item, allocation, current_lot)

    locations_visited = db.scalar(
        select(func.count(func.distinct(ScanEvent.location_id))).where(
            ScanEvent.session_id == session.id,
            ScanEvent.event_type == ScanEventType.LOCATION_SCANNED.value,
            ScanEvent.result == ScanResult.ACCEPTED.value,
        )
    ) or 0
    lots_picked = db.scalar(
        select(func.count(func.distinct(ScanEvent.picking_item_id))).where(
            ScanEvent.session_id == session.id,
            ScanEvent.event_type == ScanEventType.PICK_CONFIRMED.value,
            ScanEvent.result == ScanResult.ACCEPTED.value,
        )
    ) or 0

    return PickingExecutionSummary(
        picking_no=picking.picking_no,
        outbound_no=outbound.ob_no if outbound is not None else "--",
        picking_status=PICKING_STATUS_LABELS.get(picking.status, str(picking.status)),
        current_step=_pick_step(session),
        quantity_unit=quantity_unit,
        required_qty=required_qty,
        picked_qty=picked_qty,
        remaining_qty=max(required_qty - picked_qty, ZERO),
        current_location_code=(
            current_location.location_code if current_location is not None else None
        ),
        current_lot_no=current_lot.lot_no if current_lot is not None else None,
        current_item_required_qty=current_values[1] if current_values else None,
        current_item_picked_qty=current_values[2] if current_values else None,
        current_item_remaining_qty=(
            max(current_values[1] - current_values[2], ZERO)
            if current_values
            else None
        ),
        current_item_available_qty=current_available,
        locations_visited=int(locations_visited),
        lots_picked=int(lots_picked),
    )


def _pick_rejection(
    db: Session,
    session: ScanSession,
    user: User,
    raw_value: str,
    normalized: str,
    *,
    scan_type: ScanType,
    result: ScanResult,
    message: str,
    event_type: ScanEventType,
    matched_entity_type: str | None = None,
    matched_entity_id: int | None = None,
    location_id: int | None = None,
    picking_item_id: int | None = None,
    reference_value: str | None = None,
) -> ScanEvent:
    return _new_scan_event(
        db,
        session,
        user,
        raw_value=raw_value,
        normalized_value=normalized,
        event_type=event_type,
        scan_type=scan_type,
        result=result,
        message=message,
        matched_entity_type=matched_entity_type,
        matched_entity_id=matched_entity_id,
        location_id=location_id,
        picking_item_id=picking_item_id,
        reference_value=reference_value,
    )


def _scan_pick_value(
    db: Session, session: ScanSession, user: User, raw_value: str, normalized: str
) -> ScanEvent:
    step = _pick_step(session)
    key = normalized.lower()
    event_type = (
        ScanEventType.LOCATION_SCANNED
        if step == "EXPECT_LOCATION"
        else ScanEventType.LOT_SCANNED
    )
    expected_scan_type = (
        ScanType.LOCATION if step == "EXPECT_LOCATION" else ScanType.INVENTORY_LOT
    )
    if not normalized:
        return _pick_rejection(
            db,
            session,
            user,
            raw_value,
            normalized,
            scan_type=expected_scan_type,
            result=ScanResult.REJECTED,
            message="Scan value is empty",
            event_type=event_type,
        )
    if step == "EXPECT_QUANTITY_CONFIRMATION":
        return _pick_rejection(
            db,
            session,
            user,
            raw_value,
            normalized,
            scan_type=ScanType.UNKNOWN,
            result=ScanResult.INVALID_STATE,
            message="Confirm the selected quantity before scanning another value",
            event_type=ScanEventType.GENERIC_SCANNED,
        )

    if step == "EXPECT_LOCATION":
        locations = list(
            db.scalars(
                select(WarehouseLocation).where(
                    func.lower(WarehouseLocation.location_code) == key
                )
            ).all()
        )
        location = next(
            (row for row in locations if row.warehouse_id == session.warehouse_id),
            None,
        )
        if location is None:
            return _pick_rejection(
                db,
                session,
                user,
                raw_value,
                normalized,
                scan_type=ScanType.LOCATION,
                result=ScanResult.NOT_FOUND,
                message="Location is not available in this warehouse",
                event_type=ScanEventType.LOCATION_SCANNED,
                reference_value=normalized,
            )
        allowed = any(
            item.location_id == location.id and _item_remaining(item) > ZERO
            for item in _pick_items(db, session.picking_id)
        )
        if not allowed:
            return _pick_rejection(
                db,
                session,
                user,
                raw_value,
                normalized,
                scan_type=ScanType.LOCATION,
                result=ScanResult.WRONG_LOCATION,
                message="Location has no remaining source for this picking list",
                event_type=ScanEventType.LOCATION_SCANNED,
                matched_entity_type="WarehouseLocation",
                matched_entity_id=location.id,
                location_id=location.id,
                reference_value=location.location_code,
            )
        session.current_location_id = location.id
        session.current_picking_item_id = None
        return _new_scan_event(
            db,
            session,
            user,
            raw_value=raw_value,
            normalized_value=normalized,
            event_type=ScanEventType.LOCATION_SCANNED,
            scan_type=ScanType.LOCATION,
            result=ScanResult.ACCEPTED,
            message=f"Location {location.location_code} accepted; scan inventory lot",
            matched_entity_type="WarehouseLocation",
            matched_entity_id=location.id,
            location_id=location.id,
            reference_value=location.location_code,
        )

    lots = list(
        db.scalars(
            select(InventoryLot).where(func.lower(InventoryLot.lot_no) == key)
        ).all()
    )
    lot = next((row for row in lots if row.warehouse_id == session.warehouse_id), None)
    if lot is None:
        return _pick_rejection(
            db,
            session,
            user,
            raw_value,
            normalized,
            scan_type=ScanType.INVENTORY_LOT,
            result=ScanResult.NOT_FOUND,
            message="Inventory lot is not available in this warehouse",
            event_type=ScanEventType.LOT_SCANNED,
            reference_value=normalized,
        )
    if lot.location_id != session.current_location_id:
        return _pick_rejection(
            db,
            session,
            user,
            raw_value,
            normalized,
            scan_type=ScanType.INVENTORY_LOT,
            result=ScanResult.WRONG_LOCATION,
            message="Inventory lot is not stored at the scanned location",
            event_type=ScanEventType.LOT_SCANNED,
            matched_entity_type="InventoryLot",
            matched_entity_id=lot.id,
            location_id=lot.location_id,
            reference_value=lot.lot_no,
        )
    item = db.scalar(
        select(PickingListItem)
        .where(
            PickingListItem.picking_list_id == session.picking_id,
            PickingListItem.inventory_lot_id == lot.id,
            PickingListItem.location_id == session.current_location_id,
        )
        .order_by(PickingListItem.sequence_no, PickingListItem.id)
    )
    if item is None or _item_remaining(item) <= ZERO:
        return _pick_rejection(
            db,
            session,
            user,
            raw_value,
            normalized,
            scan_type=ScanType.INVENTORY_LOT,
            result=ScanResult.PICK_SOURCE_MISMATCH,
            message="Inventory lot is not a remaining source for this picking list",
            event_type=ScanEventType.LOT_SCANNED,
            matched_entity_type="InventoryLot",
            matched_entity_id=lot.id,
            location_id=lot.location_id,
            reference_value=lot.lot_no,
        )
    allocation = db.get(OutboundInventoryAllocation, item.outbound_allocation_id)
    if (
        lot.status not in PICKABLE_INVENTORY_STATUSES
        or allocation is None
        or allocation.outbound_order_id != session.outbound_id
        or _item_available(item, allocation, lot) <= ZERO
    ):
        return _pick_rejection(
            db,
            session,
            user,
            raw_value,
            normalized,
            scan_type=ScanType.INVENTORY_LOT,
            result=ScanResult.PICK_SOURCE_MISMATCH,
            message="Inventory lot has no pickable allocated quantity",
            event_type=ScanEventType.LOT_SCANNED,
            matched_entity_type="InventoryLot",
            matched_entity_id=lot.id,
            location_id=lot.location_id,
            picking_item_id=item.id,
            reference_value=lot.lot_no,
        )
    session.current_picking_item_id = item.id
    return _new_scan_event(
        db,
        session,
        user,
        raw_value=raw_value,
        normalized_value=normalized,
        event_type=ScanEventType.LOT_SCANNED,
        scan_type=ScanType.INVENTORY_LOT,
        result=ScanResult.ACCEPTED,
        message=f"Inventory lot {lot.lot_no} accepted; confirm quantity",
        matched_entity_type="InventoryLot",
        matched_entity_id=lot.id,
        location_id=lot.location_id,
        picking_item_id=item.id,
        reference_value=lot.lot_no,
    )


def get_scan_counters(db: Session, session_id: int) -> ScanCounters:
    rows = db.execute(
        select(ScanEvent.result, func.count(ScanEvent.id))
        .where(ScanEvent.session_id == session_id)
        .group_by(ScanEvent.result)
    ).all()
    result_counts = {str(result): int(count) for result, count in rows}
    total = sum(result_counts.values())
    accepted = result_counts.get(ScanResult.ACCEPTED.value, 0)
    duplicate = result_counts.get(ScanResult.DUPLICATE.value, 0)
    return ScanCounters(
        total=total,
        accepted=accepted,
        duplicate=duplicate,
        rejected=total - accepted - duplicate,
        result_counts=result_counts,
    )


def recent_scan_events(db: Session, session_id: int, limit: int = 20) -> list[ScanEvent]:
    return list(
        db.scalars(
            select(ScanEvent)
            .where(ScanEvent.session_id == session_id)
            .order_by(ScanEvent.scanned_at.desc(), ScanEvent.id.desc())
            .limit(limit)
        ).all()
    )


def scan_value(
    db: Session, session: ScanSession, user: User, raw_value: str
) -> ScanEvent:
    session = db.scalar(
        select(ScanSession).where(ScanSession.id == session.id).with_for_update()
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan session not found")
    normalized = normalize_scan_value(raw_value)
    if session.status != ScanSessionStatus.OPEN.value:
        resolved = ResolvedScan(
            ScanType.UNKNOWN,
            ScanResult.INVALID_STATE,
            f"Scan session is {session.status.lower()}",
        )
    elif session.operation_type == ScanOperationType.PICK.value:
        return _scan_pick_value(db, session, user, raw_value, normalized)
    elif not normalized:
        resolved = ResolvedScan(ScanType.UNKNOWN, ScanResult.REJECTED, "Scan value is empty")
    else:
        duplicate = db.scalar(
            select(ScanEvent.id).where(
                ScanEvent.session_id == session.id,
                ScanEvent.result == ScanResult.ACCEPTED.value,
                func.lower(ScanEvent.normalized_value) == normalized.lower(),
            ).limit(1)
        )
        if duplicate is not None:
            resolved = ResolvedScan(
                ScanType.UNKNOWN,
                ScanResult.DUPLICATE,
                "This value was already accepted in the current session",
                reference_value=normalized,
            )
        else:
            resolved = _resolve_candidates(db, session, user, normalized)[0]

    return _new_scan_event(
        db,
        session,
        user,
        raw_value=raw_value,
        normalized_value=normalized,
        event_type=ScanEventType.GENERIC_SCANNED,
        scan_type=resolved.scan_type,
        result=resolved.result,
        message=resolved.message,
        matched_entity_type=resolved.matched_entity_type,
        matched_entity_id=resolved.matched_entity_id,
        location_id=resolved.location_id,
        reference_value=resolved.reference_value,
    )


def confirm_pick(
    db: Session,
    session_id: int,
    payload: PickConfirmationRequest,
    user: User,
) -> ScanEvent:
    """Atomically confirm one physical pick without advancing outbound completion."""
    session = db.scalar(
        select(ScanSession).where(ScanSession.id == session_id).with_for_update()
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan session not found")
    # Re-check the caller's scope against the locked row.
    _scoped_session(db, session.id, user)
    if session.operation_type != ScanOperationType.PICK.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session is not a PICK session")

    existing = db.scalar(
        select(ScanEvent).where(
            ScanEvent.session_id == session.id,
            ScanEvent.client_operation_id == payload.client_operation_id,
        )
    )
    if existing is not None:
        return existing
    if session.status != ScanSessionStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Scan session is not open")
    if session.current_location_id is None or session.current_picking_item_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Scan a valid location and inventory lot before confirming quantity",
        )

    picking = db.scalar(
        select(PickingList)
        .where(PickingList.id == session.picking_id)
        .with_for_update()
    )
    item = db.scalar(
        select(PickingListItem)
        .where(PickingListItem.id == session.current_picking_item_id)
        .with_for_update()
    )
    if picking is None or item is None or item.picking_list_id != picking.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Picking context is no longer valid")
    if picking.status in {
        PickingStatus.COMPLETED,
        PickingStatus.CANCELED,
        PickingStatus.EXCEPTION,
    }:
        raise HTTPException(status.HTTP_409_CONFLICT, "Picking list is not open for execution")

    allocation = db.scalar(
        select(OutboundInventoryAllocation)
        .where(OutboundInventoryAllocation.id == item.outbound_allocation_id)
        .with_for_update()
    )
    lot = db.scalar(
        select(InventoryLot)
        .where(InventoryLot.id == item.inventory_lot_id)
        .with_for_update()
    )
    if allocation is None or lot is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pick source is no longer available")
    if (
        allocation.outbound_order_id != session.outbound_id
        or lot.warehouse_id != session.warehouse_id
        or lot.location_id != session.current_location_id
        or lot.status not in PICKABLE_INVENTORY_STATUSES
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Pick source context changed; scan again")

    unit, required, picked = _item_quantities(item)
    remaining = max(required - picked, ZERO)
    available = _item_available(item, allocation, lot)
    if payload.quantity > remaining:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Quantity exceeds picking remaining quantity ({remaining})",
        )
    if payload.quantity > available:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Quantity exceeds available allocated quantity ({available})",
        )

    now = datetime.now(timezone.utc)
    if unit == PickQuantityUnit.PALLET:
        item.picked_pallet_qty = picked + payload.quantity
    else:
        item.picked_carton_qty = picked + payload.quantity
    if picking.status in {PickingStatus.NEW, PickingStatus.PRINTED}:
        picking.status = PickingStatus.IN_PROGRESS
        picking.started_at = picking.started_at or now
        picking.started_by = picking.started_by or user.id

    # Make the locked item's new picked quantity visible to the completion query
    # regardless of the caller's Session autoflush configuration.
    db.flush()
    all_items = _pick_items(db, picking.id)
    if all_items and all(_item_remaining(candidate) <= ZERO for candidate in all_items):
        picking.status = PickingStatus.COMPLETED
        picking.completed_at = now
        picking.completed_by = user.id

    event = _new_scan_event(
        db,
        session,
        user,
        raw_value=str(payload.quantity),
        normalized_value=str(payload.quantity),
        event_type=ScanEventType.PICK_CONFIRMED,
        scan_type=ScanType.INVENTORY_LOT,
        result=ScanResult.ACCEPTED,
        message=(
            f"Confirmed {payload.quantity} {unit.value.lower()} for lot {lot.lot_no}"
        ),
        matched_entity_type="PickingListItem",
        matched_entity_id=item.id,
        location_id=lot.location_id,
        picking_item_id=item.id,
        reference_value=lot.lot_no,
        client_operation_id=payload.client_operation_id,
        quantity=payload.quantity,
        quantity_unit=unit,
    )
    session.current_location_id = None
    session.current_picking_item_id = None
    db.flush()
    return event


def reset_pick_step(db: Session, session: ScanSession) -> ScanSession:
    session = db.scalar(
        select(ScanSession).where(ScanSession.id == session.id).with_for_update()
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan session not found")
    if session.operation_type != ScanOperationType.PICK.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session is not a PICK session")
    if session.status != ScanSessionStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Scan session is not open")
    session.current_location_id = None
    session.current_picking_item_id = None
    db.flush()
    return session


def transition_scan_session(
    db: Session, session: ScanSession, target: ScanSessionStatus
) -> ScanSession:
    session = db.scalar(
        select(ScanSession).where(ScanSession.id == session.id).with_for_update()
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan session not found")
    if session.status != ScanSessionStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Scan session is not open")
    now = datetime.now(timezone.utc)
    session.status = target.value
    if target == ScanSessionStatus.COMPLETED:
        session.completed_at = now
    elif target == ScanSessionStatus.CANCELED:
        session.canceled_at = now
    db.flush()
    return session
