from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BOL,
    OperationalException,
    OutboundInventoryAllocation,
    OutboundOrder,
    PickingList,
    PickingListItem,
)
from app.models.bol import BOLStatus
from app.models.operational_exception import ExceptionStatus
from app.models.outbound import OBStatus
from app.models.picking import PickingStatus
from app.schemas.dispatch_readiness import DispatchReadinessCheck, DispatchReadinessRead

DISPATCH_POLICY_VERSION = "phase11.3b-outbound-v1"
DISPATCH_THROUGH_LOAD_REQUIRED = "DISPATCH_THROUGH_LOAD_REQUIRED"
LOAD_DISPATCH_REQUIRED = "LOAD_DISPATCH_REQUIRED"


def get_dispatch_readiness(db: Session, outbound: OutboundOrder) -> DispatchReadinessRead:
    allocation_count, allocated_pallet_qty = db.execute(
        select(
            func.count(OutboundInventoryAllocation.id),
            func.coalesce(func.sum(OutboundInventoryAllocation.allocated_pallet_qty), 0),
        ).where(
            OutboundInventoryAllocation.outbound_order_id == outbound.id,
            OutboundInventoryAllocation.allocated_pallet_qty > 0,
        )
    ).one()
    picked_pallet_qty = db.scalar(
        select(func.coalesce(func.sum(PickingListItem.picked_pallet_qty), 0))
        .join(PickingList, PickingList.id == PickingListItem.picking_list_id)
        .where(
            PickingList.outbound_order_id == outbound.id,
            PickingList.status != PickingStatus.CANCELED,
        )
    )
    valid_bol_count = db.scalar(
        select(func.count(BOL.id)).where(
            BOL.outbound_order_id == outbound.id,
            BOL.status.in_((BOLStatus.GENERATED, BOLStatus.PRINTED, BOLStatus.COMPLETED)),
            func.length(func.trim(BOL.bol_no)) > 0,
        )
    )
    active_exception_count = db.scalar(
        select(func.count(OperationalException.id)).where(
            OperationalException.outbound_id == outbound.id,
            OperationalException.status.in_((ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING)),
        )
    )

    allocated = Decimal(allocated_pallet_qty or 0)
    picked = Decimal(picked_pallet_qty or 0)
    check_specs = (
        ("status", "Confirmed status", outbound.status == OBStatus.CONFIRMED, "Outbound must be CONFIRMED before dispatch", None, "OUTBOUND_NOT_CONFIRMED"),
        ("allocation", "Positive allocation", allocation_count > 0 and allocated > 0, "At least one positive pallet allocation is required", "/outbound/picking", "ALLOCATION_REQUIRED"),
        ("picking", "Picking complete", allocated > 0 and picked >= allocated, "Picking is incomplete: picked pallet quantity must cover allocated pallet quantity", "/outbound/picking", "PICKING_INCOMPLETE"),
        ("bol", "Generated BOL", bool(valid_bol_count), "At least one generated BOL is required", "/outbound/bol", "SYSTEM_BOL_REQUIRED"),
        ("carrier", "Carrier assigned", outbound.carrier_id is not None, "Carrier is required before dispatch", None, "CARRIER_REQUIRED"),
        ("exceptions", "No active exception", not active_exception_count, "Resolve active outbound exceptions before dispatch", "/trouble-shoot", "ACTIVE_EXCEPTION"),
    )
    checks = [
        DispatchReadinessCheck(
            key=key,
            label=label,
        passed=passed,
        reason=None if passed else reason,
        route=route,
        code=None if passed else code,
    )
        for key, label, passed, reason, route, code in check_specs
    ]
    checks.append(DispatchReadinessCheck(key="load_dispatch", label="Transactional Load dispatch", passed=False,
        reason="Must dispatch through Load", code=LOAD_DISPATCH_REQUIRED))
    blocking_reasons = [check.reason for check in checks if check.reason]
    blocking_codes = [check.code for check in checks if check.code]
    return DispatchReadinessRead(
        status="NOT_READY" if blocking_reasons else "READY",
        error_code=DISPATCH_THROUGH_LOAD_REQUIRED,
        checks=checks,
        blocking_reasons=blocking_reasons,
        blocking_codes=blocking_codes,
    )


def require_dispatch_ready(db: Session, outbound: OutboundOrder) -> DispatchReadinessRead:
    result = get_dispatch_readiness(db, outbound)
    if result.status != "READY":
        raise HTTPException(status_code=409, detail=result.model_dump(mode="json"))
    return result
