"""Display document metadata without treating historical quantities as live stock."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models import BOL, ImportRow


def source_weight(raw):
    value = raw.get('重量(lb)')
    if value is None or isinstance(value, bool):
        return None
    try:
        weight = Decimal(str(value).replace(',', '').strip())
        return weight if weight.is_finite() and weight >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def bol_metadata(db, orders, history_ids):
    ids = [o.id for o in orders]
    if not ids:
        return {}
    raw_by_id = {r.created_entity_id: r.raw_data for r in db.scalars(
        select(ImportRow).where(ImportRow.created_entity_type == 'OUTBOUND',
                               ImportRow.created_entity_id.in_(ids),
                               ImportRow.import_job_id.in_(history_ids)).order_by(ImportRow.id)
    )}
    documents = {}
    for bol in db.scalars(select(BOL).options(selectinload(BOL.items)).where(
            BOL.outbound_order_id.in_(ids), BOL.status != 4).order_by(BOL.id.desc())):
        documents.setdefault(bol.outbound_order_id, bol)
    result = {}
    for o in orders:
        raw = raw_by_id.get(o.id, {})
        historical = o.import_job_id in history_ids
        bol = documents.get(o.id)
        weight = source_weight(raw) if historical else sum((a.allocated_weight_lbs for a in o.allocations), Decimal(0))
        if bol and bol.items:
            weight = sum((item.weight_lbs for item in bol.items), Decimal(0))
        result[o.id] = {
            # The spreadsheet's numeric BOL flag is not a document number.
            'bol_no': bol.bol_no if bol else o.bol_reference,
            'bol_type': raw.get('Type') if historical else o.ob_type,
            'group_status': raw.get('Group Status'),
            'pickup_location': o.pickup_location,
            'del_code': o.del_code or o.fc_code,
            'redirect_code': o.redirect_code,
            'transfer_code': o.transfer_code,
            'weight_lbs': weight,
            'weight_source': 'BOL' if bol and bol.items else '原表重量(lb)' if historical and weight is not None else '库存分配' if not historical else None,
        }
    return result
