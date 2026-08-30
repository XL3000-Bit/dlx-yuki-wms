from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.models import BOL, ContainerTracking, FBAShipment, Load, OperationalDocument, OperationalException, OutboundOrder, PickingList, WorkOrder
from app.models.bol import BOLStatus
from app.models.container_tracking import TrackingStatus
from app.models.fba import FBAStatus
from app.models.operational_document import DocumentStatus
from app.models.operational_exception import ExceptionStatus
from app.models.outbound import OBStatus
from app.models.picking import PickingStatus
from app.models.load import LoadStatus
from app.models.work_order import WorkOrderStatus
from app.services.access import get_access_scope


@dataclass(frozen=True)
class SearchSpec:
    type: str
    model: type
    fields: tuple
    route: str
    status_enum: type
    primary: str
    secondary: str | None = None
    options: tuple = ()


SPECS = (
    SearchSpec("CONTAINER", ContainerTracking, (ContainerTracking.container_number, ContainerTracking.mbl_number, ContainerTracking.hbl_number, ContainerTracking.filing_number, ContainerTracking.customer_reference), "/container-tracking", TrackingStatus, "container_number", "mbl_number", (joinedload(ContainerTracking.warehouse),)),
    SearchSpec("OUTBOUND", OutboundOrder, (OutboundOrder.ob_no, OutboundOrder.reference_no, OutboundOrder.appointment_reference, OutboundOrder.picking_reference, OutboundOrder.bol_reference, OutboundOrder.pod_reference), "/outbound/dispatch", OBStatus, "ob_no", "reference_no", (joinedload(OutboundOrder.warehouse), joinedload(OutboundOrder.customer))),
    SearchSpec("FBA", FBAShipment, (FBAShipment.fba_no, FBAShipment.reference_no, FBAShipment.shipment_id, FBAShipment.st_number, FBAShipment.po_number, FBAShipment.source_reference), "/fba", FBAStatus, "fba_no", "st_number", (joinedload(FBAShipment.warehouse), joinedload(FBAShipment.customer))),
    SearchSpec("PICKING", PickingList, (PickingList.picking_no,), "/outbound/picking", PickingStatus, "picking_no", None, (joinedload(PickingList.outbound).joinedload(OutboundOrder.warehouse), joinedload(PickingList.outbound).joinedload(OutboundOrder.customer))),
    SearchSpec("BOL", BOL, (BOL.bol_no,), "/outbound/bol", BOLStatus, "bol_no", None, (joinedload(BOL.warehouse), joinedload(BOL.customer), joinedload(BOL.outbound))),
    SearchSpec("LOAD", Load, (Load.load_no,), "/loads", LoadStatus, "load_no", None, (joinedload(Load.warehouse),)),
    SearchSpec("WORK_ORDER", WorkOrder, (WorkOrder.work_order_no,), "/work-orders", WorkOrderStatus, "work_order_no", None, (joinedload(WorkOrder.warehouse),)),
    SearchSpec("EXCEPTION", OperationalException, (OperationalException.exception_no, OperationalException.title), "/trouble-shoot", ExceptionStatus, "exception_no", "title", (joinedload(OperationalException.warehouse),)),
    SearchSpec("DOCUMENT", OperationalDocument, (OperationalDocument.document_no, OperationalDocument.file_name, OperationalDocument.original_file_name), "/documents", DocumentStatus, "document_no", "file_name", (joinedload(OperationalDocument.warehouse), joinedload(OperationalDocument.bol))),
)


def _status_name(enum_type: type, value) -> str:
    if isinstance(value, TrackingStatus):
        return value.value
    try:
        return enum_type(value).name
    except (ValueError, TypeError):
        return next((name for name, member in vars(enum_type).items() if name.isupper() and member == value), str(value))


def _rank(record, fields: tuple, needle: str) -> int:
    values = [str(getattr(record, field.key) or "").casefold() for field in fields]
    if hasattr(record, "bol") and getattr(record, "bol", None):
        values.append(str(record.bol.bol_no or "").casefold())
    if needle in values:
        return 1
    if any(value.startswith(needle) for value in values):
        return 2
    return 3


def _warehouse_id(record) -> int | None:
    if getattr(record, "warehouse_id", None):
        return record.warehouse_id
    parent = getattr(record, "outbound", None)
    return getattr(parent, "warehouse_id", None)


def _customer_id(record) -> int | None:
    if getattr(record, "customer_id", None):
        return record.customer_id
    parent = getattr(record, "outbound", None)
    return getattr(parent, "customer_id", None)


def search(db, query: str, limit: int, user=None) -> dict:
    scope = get_access_scope(db, user) if user is not None else None
    needle = query.casefold()
    candidates = []
    per_entity_cap = min(max(limit * 3, 20), 150)
    for spec_order, spec in enumerate(SPECS):
        pattern = f"%{query}%"
        clauses = [func.lower(field).like(pattern.casefold()) for field in spec.fields]
        stmt = select(spec.model)
        if spec.type == "DOCUMENT":
            stmt = stmt.outerjoin(BOL, BOL.id == OperationalDocument.bol_id)
            clauses.append(func.lower(BOL.bol_no).like(pattern.casefold()))
        stmt = stmt.where(or_(*clauses)).limit(per_entity_cap)
        for option in spec.options:
            stmt = stmt.options(option)
        for record in db.scalars(stmt).unique():
            if scope is not None:
                if not scope.allows_warehouse(_warehouse_id(record)):
                    continue
                if spec.type in {"OUTBOUND", "FBA", "PICKING", "BOL"} and not scope.allows_customer(_customer_id(record)):
                    continue
            candidates.append((_rank(record, spec.fields, needle), spec_order, record.id, spec, record))

    candidates.sort(key=lambda row: (row[0], row[1], row[2]))
    selected = candidates[:limit]
    grouped = []
    for spec in SPECS:
        items = []
        for rank, _, _, candidate_spec, record in selected:
            if candidate_spec is not spec:
                continue
            parent = getattr(record, "outbound", None)
            warehouse = getattr(record, "warehouse", None) or getattr(parent, "warehouse", None)
            customer = getattr(record, "customer", None) or getattr(parent, "customer", None)
            params = "selected_ob" if spec.type == "OUTBOUND" else "selected"
            route = spec.route
            if spec.type in {"CONTAINER", "OUTBOUND", "FBA", "LOAD", "WORK_ORDER", "EXCEPTION", "DOCUMENT"}:
                route = f"{route}?{params}={record.id}"
            secondary = getattr(record, spec.secondary) if spec.secondary else getattr(parent, "ob_no", None)
            if spec.type == "LOAD":
                secondary = f"{len(record.outbounds)} outbounds"
            if spec.type == "WORK_ORDER":
                secondary = record.work_order_type.value
            if spec.type == "DOCUMENT":
                secondary = record.document_type.value
            items.append({
                "type": spec.type,
                "id": record.id,
                "primary_reference": getattr(record, spec.primary),
                "secondary_reference": secondary,
                "status": _status_name(spec.status_enum, record.status if hasattr(record, "status") else record.tracking_status),
                "warehouse": warehouse.warehouse_code if warehouse else getattr(record, "delivery_warehouse_raw", None),
                "customer": customer.customer_name if customer else None,
                "target_route": route,
                "match_rank": rank,
            })
        if items:
            grouped.append({"type": spec.type, "count": len(items), "items": items})
    return {"query": query, "total": len(selected), "groups": grouped}
