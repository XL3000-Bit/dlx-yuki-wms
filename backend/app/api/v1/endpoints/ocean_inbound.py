from typing import Annotated
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from datetime import date
from app.api.deps import CurrentUser, DbSession, require_warehouse_write
from app.models import User
from app.schemas.ocean_inbound import OceanReceiptBatch, OceanPutawayBatch, OceanShipmentUpdate
from app.services.ocean_inbound import read_shipment, save_receipts, list_shipments, putaway, save_shipment

router = APIRouter(prefix="/ocean-inbound", tags=["Ocean Inbound"])
Writer = Annotated[User, Depends(require_warehouse_write)]


@router.get('')
def index(db: DbSession, user: CurrentUser, q: str = '', status: int | None = None,
          date_from: date | None = None, date_to: date | None = None,
          page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200),
          transport_status: str = '', size: str = '', trucker: str = '', container_status: str = '', team: str = '',
          scheduled_delivery_date: str = '', pod_eta: str = '', appointment: str = '',
          list_status: str = '', scheduled_from: date | None = None, scheduled_to: date | None = None,
          pod_eta_from: date | None = None, pod_eta_to: date | None = None,
          appointment_from: date | None = None, appointment_to: date | None = None,
          printed: bool | None = None, empty_reported: bool | None = None, released: bool | None = None, outbound_fully_pod: bool | None = None):
    filters = {key: value for key, value in locals().copy().items() if key in ('transport_status', 'size', 'trucker', 'container_status', 'team', 'scheduled_delivery_date', 'pod_eta', 'appointment', 'printed', 'empty_reported', 'released', 'outbound_fully_pod', 'list_status', 'scheduled_from', 'scheduled_to', 'pod_eta_from', 'pod_eta_to', 'appointment_from', 'appointment_to')}
    return list_shipments(db, user, q, status, date_from, date_to, page, per_page, filters)


@router.get("/{anchor_id}")
def detail(anchor_id: int, db: DbSession, user: CurrentUser):
    return read_shipment(db, user, anchor_id)


@router.put("/{anchor_id}/draft")
def draft(anchor_id: int, payload: OceanReceiptBatch, db: DbSession, user: Writer):
    return save_receipts(db, user, anchor_id, payload)


@router.post("/{anchor_id}/confirm")
def confirm(anchor_id: int, payload: OceanReceiptBatch, db: DbSession, user: Writer):
    return save_receipts(db, user, anchor_id, payload, confirm=True)


@router.post('/{anchor_id}/putaway')
def receive_inventory(anchor_id: int, payload: OceanPutawayBatch, db: DbSession, user: Writer):
    return putaway(db, user, anchor_id, payload)


@router.put('/{anchor_id}/shipment')
def update_shipment(anchor_id: int, payload: OceanShipmentUpdate, db: DbSession, user: Writer):
    return save_shipment(db, user, anchor_id, payload)


@router.get('/{anchor_id}/export/{kind}')
def export_shipment(anchor_id: int, kind: str, db: DbSession, user: CurrentUser):
    from app.services.uni_exports import ocean_export
    content, media, extension = ocean_export(read_shipment(db, user, anchor_id), kind)
    return Response(content, media_type=media, headers={'Content-Disposition': f'attachment; filename="Ocean-{anchor_id}-{kind}.{extension}"'})
