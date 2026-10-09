import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fillMissingExpected, receivingState } from './oceanReceivingPolicy.ts';

const locations = [{ id: 10, warehouse_id: 1, is_active: true }];
const makeRow = (receipt = {}, extra = {}) => ({
  editable: true,
  inbound: { status: 1, warehouse: { id: 1 } },
  receipt: { version: 1, expected_qty: '10.00', expected_pallets: '2', received_qty: '10', inbound_pallets: '2', location_id: 10, ...receipt },
  ...extra,
});

test('complete equal quantities are ready, including decimal representations', () => {
  assert.equal(receivingState(makeRow(), locations).stage, 'ready');
  assert.equal(receivingState(makeRow(), locations).discrepancy, false);
});

test('missing, invalid and unresolved locations block confirmation', () => {
  for (const receipt of [{ received_qty: null }, { inbound_pallets: '' }, { received_qty: '-1' }, { received_qty: 'NaN' }, { location_id: null }, { location_id: 99 }]) {
    assert.equal(receivingState(makeRow(receipt), locations).stage, 'pending');
  }
  assert.equal(receivingState(makeRow(), undefined).stage, 'pending');
  assert.equal(receivingState(makeRow(), [{ ...locations[0], warehouse_id: 2 }]).stage, 'pending');
  assert.equal(receivingState(makeRow(), [{ ...locations[0], is_active: false }]).stage, 'pending');
});

test('zero receipt is a discrepancy and requires an explicit reason', () => {
  assert.equal(receivingState(makeRow({ received_qty: '0', memo: ' ' }), locations).stage, 'pending');
  const state = receivingState(makeRow({ received_qty: '0', inbound_pallets: '0', memo: '未到货' }), locations);
  assert.equal(state.stage, 'ready');
  assert.equal(state.delta, -10);
});

test('read-only records cannot become ready; hold is not received', () => {
  assert.equal(receivingState(makeRow({}, { editable: false }), locations).stage, 'readonly');
  assert.equal(receivingState(makeRow({ confirmed_date: '2026-09-09' }, { editable: false }), locations).stage, 'received');
  assert.equal(receivingState(makeRow({}, { editable: false, inbound: { status: 2, warehouse: { id: 1 } } }), locations).stage, 'received');
});

test('batch expected fill preserves actual counts, including zero and partial receipts', () => {
  assert.deepEqual(fillMissingExpected(makeRow({ received_qty: '0', inbound_pallets: '1' }).receipt), {});
  assert.deepEqual(fillMissingExpected(makeRow({ received_qty: '4', inbound_pallets: null }).receipt), { inbound_pallets: '2' });
  assert.deepEqual(fillMissingExpected(makeRow({ received_qty: '', inbound_pallets: null }).receipt), { received_qty: '10.00', inbound_pallets: '2' });
});
