from typing import Annotated
from datetime import date, datetime, time, timedelta, UTC
from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, func, or_, cast, String, case
from app.api.deps import CurrentUser, DbSession, require_outbound_write
from app.models import User, UniBol, OutboundOrder, CargoBOL, InventoryLot, OutboundInventoryAllocation
from app.schemas.uni_bol import BolCreate, BolUpdate, LoadSelection, BolAction, PodReview, BatchPodUpload, DispatchMembership
from pydantic import ValidationError
from app.services import uni_bol as service
from app.utils.business_time import business_day_range

router = APIRouter(prefix='/uni-bols', tags=['OB BOL'])
Writer = Annotated[User, Depends(require_outbound_write)]


@router.get('')
def listing(db: DbSession, user: CurrentUser, q: str = '', status: str = '', type: str = '', shipping_mode: str = '',
            carrier_id: int | None = None, warehouse_id: int | None = None, delivery_code: str = '',
            pod_status: str = '', group_status: str = '', customer_reference: str = '', creator: str = '', confirmed: str = '',
            date_field: str = 'Created At', date_from: date | None = None, date_to: date | None = None,
            date_conditions: list[str] | None = Query(None, alias='dates[]'),
            page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=200), format: str = ''):
    if date_conditions:
        raise HTTPException(501, '日期条件已接收；组合及日期边界规则待确认，尚未执行日期查询。')
    stmt = service.scoped(db, user).join(CargoBOL, CargoBOL.fba_shipment_id == UniBol.fba_shipment_id)
    if q:
        bol_number = 'BOL' + func.lpad(cast(CargoBOL.id, String), 12, '0')
        lot_matches = select(OutboundInventoryAllocation.outbound_order_id).join(InventoryLot).where(or_(InventoryLot.lot_no.ilike(f'%{q}%'), InventoryLot.container_number.ilike(f'%{q}%')))
        stmt = stmt.where(or_(bol_number.ilike(f'%{q}%'), func.coalesce(UniBol.dispatch_ob_no, OutboundOrder.ob_no).ilike(f'%{q}%'), OutboundOrder.reference_no.ilike(f'%{q}%'), OutboundOrder.id.in_(lot_matches)))
    # This aggregate only contains FBA BOLs. Other type filters must not return FBA rows.
    if type and type != 'FBA': stmt = stmt.where(False)
    if shipping_mode: stmt = stmt.where(UniBol.details['shipping_mode'].astext == shipping_mode)
    if carrier_id: stmt = stmt.where(OutboundOrder.carrier_id == carrier_id)
    if warehouse_id: stmt = stmt.where(OutboundOrder.warehouse_id == warehouse_id)
    if delivery_code: stmt = stmt.where(OutboundOrder.fc_code.ilike(f'%{delivery_code}%'))
    if customer_reference: stmt = stmt.where(OutboundOrder.reference_no.ilike(f'%{customer_reference}%'))
    if creator: stmt = stmt.where(OutboundOrder.created_by.in_(select(User.id).where(User.display_name.ilike(f'%{creator}%'))))
    if confirmed: stmt = stmt.where(UniBol.status.in_(('Confirmed', 'In Transit', 'Delivered')) if confirmed == 'Yes' else UniBol.status.in_(('Pre', 'Canceled', 'Exception')))
    if pod_status: stmt = stmt.where(func.coalesce(UniBol.workflow['pod_status'].astext, case((UniBol.status.in_(('In Transit', 'Delivered')), 'Awaiting Upload'), else_='Not Ready')) == pod_status)
    if group_status:
        active = select(OutboundInventoryAllocation.outbound_order_id).where(OutboundInventoryAllocation.allocated_carton_qty > OutboundInventoryAllocation.completed_carton_qty)
        shipped = select(OutboundInventoryAllocation.outbound_order_id).where(OutboundInventoryAllocation.completed_carton_qty > 0)
        groups = {'In WHS': OutboundOrder.id.in_(active) & ~OutboundOrder.id.in_(shipped), 'Partial In WHS': OutboundOrder.id.in_(active) & OutboundOrder.id.in_(shipped), 'Not In WHS': ~OutboundOrder.id.in_(active)}
        stmt = stmt.where(groups.get(group_status, False))
    dates = {'Created At': UniBol.created_at, 'Actual Pickup Time': func.coalesce(UniBol.workflow['first_shipout_time'].astext, cast(OutboundOrder.actual_outbound_time, String)), 'Delivery Time': UniBol.details['delivery_time'].astext, 'Delivery Appointment Time': UniBol.details['delivery_appointment_time'].astext}
    if date_field not in dates: raise HTTPException(422, 'Unknown date field')
    from sqlalchemy import DateTime
    date_column = cast(dates[date_field], DateTime(timezone=True))
    if date_from: stmt = stmt.where(date_column >= business_day_range(date_from)[0])
    if date_to: stmt = stmt.where(date_column < business_day_range(date_to)[1])
    filtered = stmt.subquery()
    counts = dict(db.execute(select(filtered.c.status, func.count()).group_by(filtered.c.status)).all())
    counts['All'] = sum(counts.values())
    if status: stmt = stmt.where(UniBol.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    if format:
        if format != 'xlsx': raise HTTPException(422, 'Unknown export format')
        if total > 10000: raise HTTPException(422, 'Please narrow filters to 10000 BOLs or fewer')
        from app.services.uni_exports import excel
        rows = [['BOL ID', 'OB #', 'Customer Ref #', 'Group Status', 'POD Status', 'Delivery Code', 'WHS PLT', 'Created By', 'Loads', 'Shipping Mode', 'Status', 'Type', 'Payment', 'OTR Carrier', 'Scheduled Pickup Time', 'Actual Pickup Time', 'Delivery Appointment #', 'Delivery Appointment Time', 'Delivery Time', 'Remaining Qty', 'Shipped Qty', 'Remark']]
        for item in db.scalars(stmt.order_by(UniBol.id.desc())):
            r = service.serialize(db, item)
            d = r['details']
            rows.append([r['bol_no'], r['ob_no'], d.get('customer_reference'), r['group_status'], r['pod_status'], r['delivery_code'], r['whs_pallets'], r['created_by'], r['loads_count'], d.get('shipping_mode'), r['status'], r['type'], d.get('payment'), r['carrier'], d.get('scheduled_pickup_time'), r.get('actual_pickup_time'), d.get('delivery_appointment'), d.get('delivery_appointment_time'), r.get('delivery_time'), r['remaining_qty'], r['shipped_qty'], d.get('remark')])
        return Response(excel([('OB BOL', rows, [24] * len(rows[0]))]), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="OB-BOL.xlsx"'})
    return {'data': [service.serialize(db, r) for r in db.scalars(stmt.order_by(UniBol.id.desc()).offset((page-1)*per_page).limit(per_page))],
            'total': total, 'counts': counts, 'page': page, 'per_page': per_page}


@router.post('', status_code=201)
def create(payload: BolCreate, db: DbSession, user: Writer):
    return service.create(db, user, payload)


@router.get('/pod-candidates')
def pod_candidates(db: DbSession, user: CurrentUser, ob_no: str = Query('', max_length=100)):
    return service.pod_candidates(db, user, ob_no)


@router.post('/pod-batch')
def upload_batch_pod(db: DbSession, user: Writer, selection: str = Form(...), file: UploadFile = File(...)):
    try:
        payload = BatchPodUpload.model_validate_json(selection)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_context=False)) from exc
    return service.upload_batch_pod(db, user, payload, file)


@router.get('/dispatch/{ob_id}')
def dispatch_listing(ob_id: int, db: DbSession, user: CurrentUser, pool: bool = False,
                     page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=200)):
    return service.dispatch_bols(db, user, ob_id, pool, page, per_page)


@router.post('/dispatch/{ob_id}')
def dispatch_change(ob_id: int, payload: DispatchMembership, db: DbSession, user: Writer):
    return service.dispatch_membership(db, user, ob_id, payload)


@router.get('/{identity}')
def detail(identity: int, db: DbSession, user: CurrentUser):
    return service.serialize(db, service.get(db, user, identity), True)


@router.put('/{identity}')
def update(identity: int, payload: BolUpdate, db: DbSession, user: Writer):
    return service.update(db, user, identity, payload)


@router.get('/{identity}/loads')
def loads(identity: int, db: DbSession, user: CurrentUser, q: str = ''):
    return service.candidates(db, user, identity, q)


@router.post('/{identity}/loads')
def select_loads(identity: int, payload: LoadSelection, db: DbSession, user: Writer):
    return service.select_loads(db, user, identity, payload)


@router.post('/{identity}/actions')
def action(identity: int, payload: BolAction, db: DbSession, user: Writer):
    return service.action(db, user, identity, payload)


@router.post('/{identity}/pod')
def upload_pod(identity: int, db: DbSession, user: Writer, version: int = Form(...), file: UploadFile = File(...),
               delivery_date: date | None = Form(None), delivery_appointment: str = Form('', max_length=100)):
    metadata = {'delivery_date': delivery_date.isoformat(), 'delivery_appointment': delivery_appointment.strip()} if delivery_date else None
    return service.upload_pod(db, user, identity, version, file, metadata)


@router.post('/{identity}/pod/review')
def review_pod(identity: int, payload: PodReview, db: DbSession, user: Writer):
    return service.review_pod(db, user, identity, payload)


@router.get('/{identity}/export/{kind}')
def export_bol(identity: int, kind: str, db: DbSession, user: CurrentUser):
    from app.services.uni_exports import bol_export
    row = service.serialize(db, service.get(db, user, identity), True)
    content, media, extension = bol_export(row, kind)
    return Response(content, media_type=media, headers={'Content-Disposition': f'attachment; filename="{row["bol_no"]}.{extension}"'})
