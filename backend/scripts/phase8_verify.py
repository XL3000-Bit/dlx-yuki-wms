from sqlalchemy import func, or_, select
from app.db.session import SessionLocal
from app.models import AuditLog, FBAInventoryAllocation, FBAShipment, ImportJob, InboundRecord, InventoryLot, OutboundInventoryAllocation, OutboundOrder
from app.models.import_job import ImportStatus

with SessionLocal() as session:
    negative = session.scalar(select(func.count()).select_from(InventoryLot).where(or_(
        InventoryLot.available_pallet_qty < 0, InventoryLot.available_carton_qty < 0,
        InventoryLot.available_weight_lbs < 0, InventoryLot.available_cbm < 0,
        InventoryLot.allocated_pallet_qty < 0, InventoryLot.allocated_carton_qty < 0,
    )))
    values = {
        "NEGATIVE_INVENTORY_ROWS": negative,
        "COMPLETED_IMPORT_JOBS": session.scalar(select(func.count()).select_from(ImportJob).where(ImportJob.status == ImportStatus.COMPLETED)),
        "TRACED_INBOUND_ROWS": session.scalar(select(func.count()).select_from(InboundRecord).where(InboundRecord.import_row_id.is_not(None))),
        "INVENTORY_LOTS": session.scalar(select(func.count()).select_from(InventoryLot)),
        "FBA_SHIPMENTS": session.scalar(select(func.count()).select_from(FBAShipment)),
        "FBA_ALLOCATIONS": session.scalar(select(func.count()).select_from(FBAInventoryAllocation)),
        "OUTBOUND_ORDERS": session.scalar(select(func.count()).select_from(OutboundOrder)),
        "OUTBOUND_ALLOCATIONS": session.scalar(select(func.count()).select_from(OutboundInventoryAllocation)),
        "IMPORT_AUDITS": session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action.like("IMPORT%"))),
    }
    for key, value in values.items(): print(f"{key}={value}")
