"""Explain source-link candidates without changing records or inventory."""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re

from app.services.wps_duplicates import identity_key
from app.services.wps_review import quantity


def text(value):
    return str(value).strip().upper() if value is not None and str(value).strip() else None


def day(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date().isoformat()
    except ValueError:
        return None


def rounded(value, places):
    value = quantity(value)
    try:
        return value.quantize(Decimal(places), rounding=ROUND_HALF_UP) if value is not None else None
    except InvalidOperation:
        return None


def references(value):
    # Preserve ordering and duplicates; only normalize known list separators.
    values = value if isinstance(value, list) else [value]
    return tuple(part.strip().upper() for item in values if item is not None
                 for part in re.split(r'[,，\r\n]+', str(item)) if part.strip())


def confirmation_token(row, record, warehouse_id):
    data = [row['sourceIdentity'], row['values'], row.get('customerId'), warehouse_id,
            row['duplicateCheck'], record.source_metadata, str(getattr(record, 'updated_at', None))]
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def annotate_link_review(sheets, records, warehouse_id):
    records_by_id = {r.id: r for r in records}
    claims = defaultdict(list)
    counts = Counter()
    for sheet in sheets:
        for row in sheet['rows']:
            if sheet['sheet'] != 'OL':
                continue
            check = row['duplicateCheck']
            source = identity_key(row.get('sourceIdentity'))
            compatible = []
            for candidate in check['candidates']:
                record = records_by_id[candidate['id']]
                values = row['values']
                fields = [
                    ('container', values.get('container_number'), record.container_number, text),
                    ('customer', row.get('customerId'), record.customer_id, text),
                    ('warehouse', warehouse_id, record.warehouse_id, text),
                    ('destination', values.get('destination'), record.fc_code, text),
                    ('cartons', values.get('carton_qty'), record.carton_qty, quantity),
                    ('pallets', values.get('pallet_qty'), record.pallet_qty, quantity),
                    ('unloadDate', values.get('unload_date'), getattr(record, 'unload_date', None), day),
                    # Location stays literal: A01-2P must not silently become A01.
                    ('location', values.get('raw_location_text'), record.raw_location_text, text),
                    ('weight', values.get('weight_lbs'), getattr(record, 'weight_lbs', None), lambda v: rounded(v, '.01')),
                    ('cbm', values.get('cbm'), getattr(record, 'cbm', None), lambda v: rounded(v, '.0001')),
                    ('fba', values.get('fba_references'), getattr(record, 'fba_reference', None), references),
                    ('po', values.get('po_numbers'), getattr(record, 'po_number', None), references),
                    ('receivedDate', values.get('received_date'), getattr(record, 'received_date', None), day),
                ]
                comparisons = []
                for field, wps_value, yuki_value, normalize in fields:
                    left, right = normalize(wps_value), normalize(yuki_value)
                    both_empty = field == 'receivedDate' and wps_value in (None, '') and yuki_value in (None, '')
                    comparisons.append({'field': field, 'wps': str(wps_value) if wps_value is not None else None,
                                        'yuki': str(yuki_value) if yuki_value is not None else None,
                                        'status': 'equal' if both_empty else 'missing' if left is None or right is None else
                                        'equal' if left == right else 'different'})
                metadata = record.source_metadata or {}
                linked = identity_key(metadata.get('sourceIdentity')) if isinstance(metadata, dict) else None
                candidate['comparison'] = comparisons
                candidate['linkedToOtherSource'] = bool(linked and linked != source)
                if all(c['status'] == 'equal' for c in comparisons) and not candidate['linkedToOtherSource']:
                    compatible.append(candidate['id'])
            status = 'needs_comparison'
            selected = None
            if check['status'] in ('invalid_source', 'duplicate_source', 'source_conflict', 'missing_container'):
                status = 'source_blocked'
            elif check['status'] == 'source_linked':
                status = 'already_linked'
            elif not sheet.get('complete') or sheet.get('missingFields'):
                status = 'snapshot_incomplete'
            elif row.get('customerId') is None:
                status = 'customer_required'
            elif warehouse_id is None:
                status = 'warehouse_required'
            elif not check['candidateCount']:
                status = 'no_candidate'
            elif check['candidateCount'] > len(check['candidates']):
                status = 'too_many_candidates'
            elif len(compatible) > 1:
                status = 'multiple_matches'
            elif len(compatible) == 1:
                status, selected = 'ready_for_review', compatible[0]
            row['linkReview'] = {'status': status, 'suggestedInboundId': selected, 'written': False}
            if selected is not None:
                row['linkReview']['confirmationToken'] = confirmation_token(row, records_by_id[selected], warehouse_id)
                claims[selected].append(row)
    # One-to-one only: two source rows must not silently claim the same inbound.
    for rows in claims.values():
        if len(rows) > 1:
            for row in rows:
                row['linkReview'].update(status='shared_candidate', suggestedInboundId=None)
    for sheet in sheets:
        if sheet['sheet'] == 'OL':
            counts.update(row['linkReview']['status'] for row in sheet['rows'])
    return {'counts': dict(counts), 'databaseWritten': False, 'confirmationRequired': True}
