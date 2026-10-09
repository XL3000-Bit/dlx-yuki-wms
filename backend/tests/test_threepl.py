from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.inbound import InboundRecord, InboundStatus
from app.models.inventory import InventoryLot, InventoryStatus
from app.models.outbound import OBStatus, OutboundInventoryAllocation, OutboundOrder
from app.models.operational_exception import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    OperationalException,
)
from app.models.work_order import WorkOrder, WorkOrderPriority, WorkOrderStatus, WorkOrderType
from app.utils.business_time import get_business_now, get_business_today


def test_threepl_overview_aggregates_client_operations(client, db: Session, seed):
    today = get_business_today()
    inbound = InboundRecord(
        inbound_no="IB-3PL-001",
        container_number="CONT-3PL-001",
        customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id,
        received_date=today,
        pallet_qty=Decimal("12"),
        carton_qty=Decimal("240"),
        status=InboundStatus.COMPLETED,
        created_by=seed["admin"].id,
    )
    db.add(inbound)
    db.flush()

    lot = InventoryLot(
        lot_no="LOT-3PL-001",
        customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id,
        source_inbound_id=inbound.id,
        container_number=inbound.container_number,
        original_pallet_qty=Decimal("12"),
        original_carton_qty=Decimal("240"),
        original_weight_lbs=Decimal("1200"),
        original_cbm=Decimal("24"),
        available_pallet_qty=Decimal("8"),
        available_carton_qty=Decimal("160"),
        available_weight_lbs=Decimal("800"),
        available_cbm=Decimal("16"),
        allocated_pallet_qty=Decimal("2"),
        allocated_carton_qty=Decimal("40"),
        allocated_weight_lbs=Decimal("200"),
        allocated_cbm=Decimal("4"),
        hold_pallet_qty=Decimal("2"),
        hold_carton_qty=Decimal("40"),
        inbound_date=today - timedelta(days=40),
        status=InventoryStatus.PARTIALLY_ALLOCATED,
        created_by=seed["admin"].id,
    )
    db.add(lot)
    db.flush()

    outbound = OutboundOrder(
        ob_no="OB-3PL-001",
        customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id,
        status=OBStatus.COMPLETED,
        completed_at=get_business_now(),
        created_by=seed["admin"].id,
    )
    db.add(outbound)
    db.flush()
    db.add(OutboundInventoryAllocation(
        outbound_order_id=outbound.id,
        inventory_lot_id=lot.id,
        allocated_pallet_qty=Decimal("2"),
        allocated_carton_qty=Decimal("40"),
        allocated_weight_lbs=Decimal("200"),
        allocated_cbm=Decimal("4"),
        completed_pallet_qty=Decimal("2"),
        completed_carton_qty=Decimal("40"),
        completed_weight_lbs=Decimal("200"),
        completed_cbm=Decimal("4"),
        created_by=seed["admin"].id,
    ))
    db.commit()

    response = client.get(
        "/api/v1/3pl/overview",
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "active_clients": 1,
        "inventory_pallets": 12.0,
        "inventory_cartons": 240.0,
        "inventory_cbm": 20.0,
        "hold_pallets": 2.0,
        "open_inbounds": 0,
        "open_outbounds": 0,
    }
    assert payload["usage"]["receiving_orders"] == 1
    assert payload["usage"]["receiving_pallets"] == 12.0
    assert payload["usage"]["outbound_orders"] == 1
    assert payload["usage"]["outbound_pallets"] == 2.0
    assert payload["usage"]["storage_pallet_days"] == 12.0
    assert payload["clients"][0]["oldest_inventory_days"] >= 40
    assert {item["title"] for item in payload["attention"]} >= {
        "Inventory on hold",
        "Aging inventory",
        "Missing billing contact",
    }


def test_threepl_overview_rejects_invalid_date_range(client):
    response = client.get(
        "/api/v1/3pl/overview",
        params={"date_from": "2026-09-02", "date_to": "2026-09-01"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "date_to must be on or after date_from"


def test_threepl_dispatch_queue_prioritizes_blockers_and_links_actions(client, db: Session, seed):
    now = get_business_now()
    blocked = OutboundOrder(
        ob_no="OB-3PL-BLOCKED",
        customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id,
        carrier_id=seed["carrier"].id,
        status=OBStatus.IN_PROGRESS,
        schedule_pickup_at=now + timedelta(hours=4),
        created_by=seed["admin"].id,
    )
    ready = OutboundOrder(
        ob_no="OB-3PL-READY",
        customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id,
        carrier_id=seed["carrier"].id,
        status=OBStatus.IN_PROGRESS,
        schedule_pickup_at=now + timedelta(days=3),
        loading_team="Outbound A",
        created_by=seed["admin"].id,
    )
    db.add_all([blocked, ready])
    db.flush()
    work_order = WorkOrder(
        work_order_no="WO-3PL-001",
        work_order_type=WorkOrderType.LOAD,
        status=WorkOrderStatus.ASSIGNED,
        warehouse_id=seed["warehouse"].id,
        outbound_id=blocked.id,
        priority=WorkOrderPriority.HIGH,
        assigned_to=seed["admin"].id,
        scheduled_at=now + timedelta(hours=3),
        created_by=seed["admin"].id,
    )
    exception = OperationalException(
        exception_no="EX-3PL-001",
        exception_type=ExceptionType.APPOINTMENT,
        severity=ExceptionSeverity.CRITICAL,
        status=ExceptionStatus.OPEN,
        title="Appointment confirmation missing",
        description="Client confirmation is required before loading.",
        warehouse_id=seed["warehouse"].id,
        outbound_id=blocked.id,
        reported_at=now,
        reported_by=seed["admin"].id,
    )
    db.add_all([work_order, exception])
    db.commit()

    response = client.get("/api/v1/3pl/dispatch-queue")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total": 2,
        "ready": 1,
        "at_risk": 0,
        "blocked": 1,
        "overdue": 0,
        "unassigned": 0,
    }
    first, second = payload["tasks"]
    assert first["reference"] == "OB-3PL-BLOCKED"
    assert first["queue_state"] == "BLOCKED"
    assert first["priority"] == "URGENT"
    assert first["owner_name"] == "Admin"
    assert first["blocker"] == "Appointment confirmation missing"
    assert first["action_target"] == f"/trouble-shoot?selected={exception.id}"
    assert second["reference"] == "OB-3PL-READY"
    assert second["queue_state"] == "READY"
    assert second["action_target"] == f"/outbound/dispatch?selected_ob={ready.id}"
