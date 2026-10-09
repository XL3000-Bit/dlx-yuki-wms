"""Atomic, repeatable conversion of archived rows; never creates inventory."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, text
from app.models import ImportJob, ImportRow, Customer, InboundRecord, FBAShipment, OutboundOrder, InventoryLot, AuditLog
from app.models.container_tracking import ContainerTracking, TrackingStatus

PROFILE = 'WEST_COAST_4_0_HISTORY'

def parse_date(value):
    if not value: return None
    value = str(value).strip()
    zone = ZoneInfo('America/Los_Angeles')
    for suffix, hours in [('PDT', -7), ('PST', -8), ('MDT', -6), ('MST', -7)]:
        if value.endswith(suffix):
            value = value[:-3].strip(); zone = timezone(timedelta(hours=hours)); break
    try: result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        result = None
        for fmt in ('%Y/%m/%d', '%m/%d/%Y %H:%M', '%m/%d/%Y', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M'):
            try: result = datetime.strptime(value, fmt); break
            except ValueError: pass
        if result is None: return None
    return result if result.tzinfo else result.replace(tzinfo=zone)

def convert(db, user_id, warehouse_id):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('west-history-convert'))"))
    stock_before = db.scalar(select(func.count()).select_from(InventoryLot))
    customers = {c.customer_name:c.id for c in db.scalars(select(Customer))}
    counts, skipped, issues = Counter(), Counter(), []
    def customer(value):
        name = str(value or '').strip()
        if not name: return None
        if name not in customers:
            c = Customer(customer_code='HIST-'+hashlib.sha256(name.encode()).hexdigest()[:16], customer_name=name, is_active=True)
            db.add(c); db.flush(); customers[name] = c.id
        return customers[name]
    jobs = db.scalars(select(ImportJob).where(ImportJob.profile_code == PROFILE).order_by(ImportJob.id)).all()
    for job in jobs:
        if job.source_sheet not in ('提柜','OL','DS','出库'): continue
        rows = db.scalars(select(ImportRow).where(ImportRow.import_job_id == job.id).order_by(ImportRow.row_number)).all()
        for row in rows:
            if row.created_entity_id:
                skipped[job.source_sheet] += 1; continue
            d = row.raw_data
            def val(k):
                v = d.get(k)
                return str(v).strip() if v is not None and str(v).strip() else None
            def dt(k):
                result = parse_date(d.get(k))
                if d.get(k) and result is None: issues.append({'row_id':row.id, 'field':k, 'reason':'unparsed date; original retained'})
                return result
            def qty(k):
                v = val(k)
                if v is None: return Decimal(0)
                try:
                    n = Decimal(v.replace(',',''))
                    if not n.is_finite() or n < 0 or n >= 1000000000: raise InvalidOperation
                    return n
                except InvalidOperation:
                    issues.append({'row_id':row.id,'field':k,'reason':'invalid quantity; original retained'})
                    return Decimal(0)
            metadata = {'mode':'HISTORY_PENDING_RECONCILIATION', 'import_job_id':job.id, 'import_row_id':row.id, 'source_sheet':job.source_sheet, 'source_row':row.row_number}
            # All original fields are also visible in the business detail remark.
            remark = '【历史转换 · 库存待核对】原表 '+job.source_sheet+' 第 '+str(row.row_number)+' 行\n'+json.dumps(d, ensure_ascii=False, indent=2)
            common = dict(warehouse_id=warehouse_id, import_job_id=job.id)
            if job.source_sheet == '提柜':
                state = TrackingStatus.COMPLETED if val('状态') == '已完成' else TrackingStatus.WAREHOUSE_RECEIVED if val('实际到仓日期') else TrackingStatus.IN_TRANSIT
                obj = ContainerTracking(**common, container_number=val('柜号') or f'UNKNOWN-{row.id}', mbl_number=val('MBL'), customer_reference=val('客户'), pod_eta=dt('ETA'), pod=val('码头'), scheduled_delivery_at=dt('预计到仓时间'), actual_delivery_at=dt('实际到仓日期'), wa_received_at=dt('实际到仓日期'), wa_complete_at=dt('完成拆柜日期'), wa_empty_at=dt('还空时间'), tracking_status=state, container_attributes=val('柜型'), container_remark=remark, source_type='WEST_COAST_4_0_HISTORY', source_file_name=job.original_file_name, source_row_number=row.row_number, source_fingerprint=hashlib.sha256(f'{job.file_hash}:{job.source_sheet}:{row.row_number}'.encode()).hexdigest())
                kind, number = 'CONTAINER_TRACKING', obj.container_number
            elif job.source_sheet == 'OL':
                unloaded, received = dt('拆柜时间'), dt('实际到仓时间')
                obj = InboundRecord(**common, inbound_no=f'HIB{row.id:010}', customer_id=customer(val('客户')), container_number=val('柜号') or f'UNKNOWN-{row.id}', fc_code=val('仓点'), pallet_qty=qty('板数'), carton_qty=qty('件数'), weight_lbs=qty('磅数(lb)') if val('磅数(lb)') is not None else qty('重量(kg)')*Decimal('2.2046226218'), cbm=qty('体积'), raw_location_text=val('库位'), po_number=val('PO'), fba_reference=val('FBA'), unload_date=unloaded.date() if unloaded else None, received_date=received.date() if received else None, status=5, source_metadata=metadata, import_row_id=row.id, remark=remark, created_by=user_id)
                kind, number = 'INBOUND', obj.inbound_no
            elif job.source_sheet == 'DS':
                obj = FBAShipment(**common, fba_no=f'HFBA{row.id:010}', customer_id=customer(val('客户')), amazon_fc_code=val('派送仓点') or 'UNKNOWN', shipment_id=val('FBA'), po_number=val('PO'), source_reference=val('柜号-仓点'), reference_no=val('柜号'), status=8, remark=remark, created_by=user_id)
                metadata['historical_quantities'] = {k:d.get(k) for k in ('件数','重量','体积','LBS')}
                kind, number = 'FBA', obj.fba_no
            else:
                obj = OutboundOrder(**common, ob_no=f'HOB{row.id:010}', fc_code=val('仓点'), reference_no=val('单号-仓点'), appointment_reference=val('ISA/预约编号'), delivery_appointment_time=dt('预计送仓时间'), actual_outbound_time=dt('出库时间'), po_number=val('PO'), loading_team=val('装载人'), truck_type=val('装载'), agent_code=val('账号'), redirect_code=val('Redirect Code'), status=1, ob_type='FBA', remark=remark, created_by=user_id)
                metadata['historical_quantities'] = {k:d.get(k) for k in ('预计板数','预计件数','预计重量','预计体积','真实板数','真实件数','真实重量','真实体积')}
                kind, number = 'OUTBOUND', obj.ob_no
            db.add(obj); db.flush()
            row.created_entity_type = kind; row.created_entity_id = obj.id
            row.mapped_data = {**metadata, 'business_no':number}
            counts[job.source_sheet] += 1
        job.options = {**(job.options or {}), 'conversion_mode':'HISTORY_PENDING_RECONCILIATION'}
    assert db.scalar(select(func.count()).select_from(InventoryLot)) == stock_before
    report = {'created':dict(counts), 'already_converted':dict(skipped), 'inventory_before':stock_before, 'inventory_after':stock_before, 'issues':issues}
    if counts:
        db.add(AuditLog(user_id=user_id, action='CONVERT_HISTORY', entity_type='IMPORT', after_data=report))
    db.flush()
    return report
