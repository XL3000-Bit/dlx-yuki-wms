from datetime import date
from types import SimpleNamespace

import pytest

from app.services.wps_duplicates import annotate_duplicates
from app.services.wps_link_review import annotate_link_review


def row(key='1'):
    return {'sourceIdentity': {'documentId': 'doc', 'sheetId': 'ol', 'recordId': key},
            'customerId': 1, 'values': {'container_number': ' box ', 'destination': 'ont8',
            'carton_qty': '10.00', 'pallet_qty': '1', 'unload_date': '2026-09-01T00:00:00Z',
            'weight_lbs': '22.046226', 'cbm': '1.2', 'raw_location_text': 'A01-2P'}}


def record(key=1):
    return SimpleNamespace(id=key, inbound_no=f'IB-{key}', container_number='BOX',
        customer_id=1, warehouse_id=1, fc_code='ONT8', carton_qty=10, pallet_qty=1,
        weight_lbs='22.05', cbm='1.2000', unload_date=date(2026, 9, 1), raw_location_text='A01-2P', source_metadata=None, status=1)


def check(rows, records, warehouse=1, complete=True):
    sheets = [{'sheet': 'OL', 'complete': complete, 'rows': rows}]
    annotate_duplicates(sheets, records)
    result = annotate_link_review(sheets, records, warehouse)
    assert result['databaseWritten'] is False
    return [r['linkReview']['status'] for r in rows]


def test_matching_fields_only_suggest_manual_review():
    item, history = row(), record()
    assert check([item], [history]) == ['ready_for_review']
    assert item['linkReview']['suggestedInboundId'] == 1
    assert history.source_metadata is None


@pytest.mark.parametrize('field,value', [('weight_lbs', '23'), ('cbm', None),
    ('fba_references', ['FBA1']), ('po_numbers', ['PO1']), ('received_date', 'invalid')])
def test_extended_fields_block_mismatched_confirmation(field, value):
    item = row()
    item['values'][field] = value
    assert check([item], [record()]) == ['needs_comparison']


def test_reference_lists_preserve_duplicates_and_order():
    item, history = row(), record()
    item['values']['fba_references'] = ['FBA1', 'FBA1', 'FBA2']
    history.fba_reference = 'FBA1, FBA1, FBA2'
    assert check([item], [history]) == ['ready_for_review']
    history.fba_reference = 'FBA1, FBA2'
    assert check([item], [history]) == ['needs_comparison']


@pytest.mark.parametrize('field,value', [('carton_qty', None), ('pallet_qty', 'NaN'),
    ('raw_location_text', 'A01'), ('unload_date', '2026-09-01garbage')])
def test_missing_or_different_values_prevent_match(field, value):
    item = row()
    item['values'][field] = value
    assert check([item], [record()]) == ['needs_comparison']


def test_one_inbound_cannot_be_suggested_for_two_rows():
    assert check([row('1'), row('2')], [record()]) == ['shared_candidate', 'shared_candidate']
    assert check([row()], [record(1), record(2)]) == ['multiple_matches']


def test_existing_source_ownership_and_changes_are_visible():
    history = record()
    history.source_metadata = {'sourceIdentity': row('other')['sourceIdentity']}
    item = row()
    assert check([item], [history]) == ['needs_comparison']
    assert item['duplicateCheck']['candidates'][0]['linkedToOtherSource']
    history.source_metadata = {'sourceIdentity': item['sourceIdentity']}
    history.carton_qty = 99
    assert check([item], [history]) == ['already_linked']
    assert any(c['status'] == 'different' for c in item['duplicateCheck']['candidates'][0]['comparison'])


def test_required_context_and_truncated_candidates():
    assert check([row()], [record()], warehouse=None) == ['warehouse_required']
    assert check([row()], [record()], complete=False) == ['snapshot_incomplete']
    item = row()
    item['customerId'] = None
    assert check([item], [record()]) == ['customer_required']
    assert check([row()], [record(i) for i in range(11)]) == ['too_many_candidates']
    assert check([row()], []) == ['no_candidate']
    assert check([row(), row()], [record()]) == ['source_blocked', 'source_blocked']
