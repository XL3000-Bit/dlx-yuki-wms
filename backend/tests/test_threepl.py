from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.inbound import InboundRecord, InboundStatus
from app.models.inventory import InventoryLot, InventoryStatus
from app.models.outbound import OBStatus, OutboundInventoryAllocation, OutboundOrder


def test_threepl_overview_aggregates_client_operations(client, db: Session, seed):
    today = date.today()
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
        completed_at=datetime.now(timezone.utc),
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
