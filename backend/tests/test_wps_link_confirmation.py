import json
from datetime import date

import pytest
from sqlalchemy import select, func

from app.api.v1.endpoints import wps_review
from app.core.security import create_access_token
from app.models.inbound import InboundRecord, AuditLog
from app.models.inventory import InventoryLot


@pytest.fixture
def proposal(client, db, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(wps_review, 'SNAPSHOT_DIR', tmp_path)
    row = {'sourceIdentity': {'documentId': 'doc', 'sheetId': 'ol', 'recordId': '1'},
           'values': {'customer': 'ACME', 'container_number': 'BOX', 'destination': 'ONT8',
                      'carton_qty': 10, 'pallet_qty': 1, 'weight_lbs': 22.046226, 'cbm': 1.2,
                      'unload_date': '2026-09-01', 'raw_location_text': 'A01-2P',
                      'location_candidates': ['A01'], 'fba_references': ['FBA1'], 'po_numbers': ['PO1']},
           'issues': [], 'rawFields': {}}
    for name, filename, rows in [('OL', 'ol-normalized.json', [row]), ('提柜', 'inbound-normalized.json', [])]:
        (tmp_path / filename).write_text(json.dumps({'mode': 'normalized_preview_only',
            'customerScope': 'all', 'sheet': name, 'complete': True, 'rows': rows, 'missingFields': []}), encoding='utf-8')
    record = InboundRecord(inbound_no='IB-LINK', container_number='BOX',
        customer_id=seed['customer'].id, warehouse_id=seed['warehouse'].id, created_by=seed['admin'].id,
        fc_code='ONT8', carton_qty=10, pallet_qty=1, weight_lbs=22.05, cbm=1.2,
        unload_date=date(2026, 9, 1), raw_location_text='A01-2P', fba_reference='FBA1', po_number='PO1',
        source_metadata={'mode': 'HISTORY_PENDING_RECONCILIATION'})
    db.add(record)
    db.flush()
    lot = InventoryLot(lot_no='LOT-LINK', source_inbound_id=record.id, container_number='BOX',
        warehouse_id=record.warehouse_id, customer_id=record.customer_id, created_by=seed['admin'].id,
        raw_location_text='A01-2P', original_pallet_qty=1, original_carton_qty=10,
        original_weight_lbs=22.05, original_cbm=1.2, available_pallet_qty=1,
        available_carton_qty=10, available_weight_lbs=22.05, available_cbm=1.2)
    db.add(lot)
    db.commit()
    result = client.post('/api/v1/wps/review', json={'warehouse_id': record.warehouse_id})
    assert result.status_code == 200, result.text
    reviewed = result.json()['sheets'][0]['rows'][0]
    assert reviewed['linkReview']['status'] == 'ready_for_review'
    payload = {'warehouse_id': record.warehouse_id, 'source_identity': row['sourceIdentity'],
               'inbound_id': record.id, 'confirmation_token': reviewed['linkReview']['confirmationToken']}
    return payload, record, lot, tmp_path


def test_confirmation_preserves_inventory_and_rejects_replay(client, db, proposal):
    payload, record, lot, _ = proposal
    db.refresh(lot)
    db.refresh(record)
    before = {c.name: getattr(lot, c.name) for c in lot.__table__.columns}
    record_before = {c.name: getattr(record, c.name) for c in record.__table__.columns
                     if c.name not in ('source_metadata', 'updated_at')}
    response = client.post('/api/v1/wps/links/confirm', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['inventoryWritten'] is False
    db.refresh(record)
    db.refresh(lot)
    assert before == {c.name: getattr(lot, c.name) for c in lot.__table__.columns}
    assert record_before == {name: getattr(record, name) for name in record_before}
    assert record.source_metadata['mode'] == 'HISTORY_PENDING_RECONCILIATION'
    assert record.source_metadata['sourceIdentity'] == payload['source_identity']
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1
    assert client.post('/api/v1/wps/links/confirm', json=payload).status_code == 409
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1


@pytest.mark.parametrize('change', ['record', 'snapshot', 'candidate', 'token'])
def test_stale_or_wrong_confirmation_is_rejected(client, db, proposal, change):
    payload, record, _, path = proposal
    if change == 'record':
        record.carton_qty = 11
        db.commit()
    elif change == 'snapshot':
        file = path / 'ol-normalized.json'
        data = json.loads(file.read_text(encoding='utf-8'))
        data['rows'][0]['values']['po_numbers'] = ['OTHER']
        file.write_text(json.dumps(data), encoding='utf-8')
    elif change == 'candidate':
        payload['inbound_id'] += 100
    else:
        payload['confirmation_token'] = '0' * 64
    assert client.post('/api/v1/wps/links/confirm', json=payload).status_code == 409
    db.refresh(record)
    assert 'sourceIdentity' not in record.source_metadata
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_confirmation_requires_admin(client, seed, proposal):
    payload = proposal[0]
    client.headers['Authorization'] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    assert client.post('/api/v1/wps/links/confirm', json=payload).status_code == 403
    client.headers.pop('Authorization')
    assert client.post('/api/v1/wps/links/confirm', json=payload).status_code == 401
