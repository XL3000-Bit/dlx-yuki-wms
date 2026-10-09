import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseCell, parseSheetPaste, pasteTargets, oceanEditableFields } from './oceanSpreadsheet.ts';

const locations = [
  { id: 1, warehouse_id: 1, is_active: true, location_code: 'A-01' },
  { id: 2, warehouse_id: 2, is_active: true, location_code: 'B-01' },
  { id: 3, warehouse_id: 1, is_active: false, location_code: 'OLD' },
];
test('spreadsheet clipboard preserves blanks, quoted tabs, multiline text and escaped quotes', () => {
  assert.deepEqual(parseSheetPaste('10\t\tA-01\r\n0\t2\tB-01\r\n'), [['10', '', 'A-01'], ['0', '2', 'B-01']]);
  assert.deepEqual(parseSheetPaste('"hello\tworld"\t"line1\nline2 ""ok"""\n'), [['hello\tworld', 'line1\nline2 "ok"']]);
  assert.deepEqual(parseSheetPaste('1\t\n'), [['1', '']]);
});
test('Ocean paste skips read-only columns and cannot write hidden fields', () => {
  const rows = [{ id: 1, editable: true }];
  const targets = pasteTargets(rows, 0, 'received_qty', [['12', '2', 'A-01', '3', 'memo']], oceanEditableFields);
  assert.deepEqual(targets.map(x => x.field), ['received_qty', 'inbound_pallets', 'location_id', 'markup_pallets', 'memo']);
  assert.throws(() => pasteTargets(rows, 0, 'memo', [['memo', 'hidden']], oceanEditableFields));
  assert.throws(() => pasteTargets(rows, 0, 'estimated_pallets', [['1']], oceanEditableFields));
  assert.throws(() => pasteTargets(rows, 0, 'received_qty', [], oceanEditableFields));
});
test('malformed or oversized clipboard is rejected before editing', () => {
  for (const text of ['"open', '"closed"extra', '1\t2\n3', 'a'.repeat(1000001), 'x\n'.repeat(1001)]) assert.throws(() => parseSheetPaste(text));
});
test('manual locations resolve only uniquely in the active warehouse', () => {
  assert.deepEqual(parseCell('location_id', ' a-01 ', 1, locations).patch, { location_id: 1 });
  for (const raw of ['B-01', 'OLD', 'unknown']) assert.ok(parseCell('location_id', raw, 1, locations).error);
  assert.ok(parseCell('location_id', 'A-01', 1, undefined).error);
  assert.ok(parseCell('location_id', 'A-01', 1, [...locations, { ...locations[0], id: 4 }]).error);
  assert.deepEqual(parseCell('location_id', '', 1, locations).patch, { location_id: null });
});
test('numeric values do not silently round, accept negatives, or turn blanks into zero', () => {
  for (const value of ['-1', '1.001', 'NaN', 'Infinity', '1e3', '1,000', '10000000000']) assert.ok(parseCell('received_qty', value, 1, locations).error);
  assert.deepEqual(parseCell('received_qty', '0', 1, locations).patch, { received_qty: '0' });
  assert.deepEqual(parseCell('received_qty', '', 1, locations).patch, { received_qty: null });
  assert.deepEqual(parseCell('received_qty', '9999999999.99', 1, locations).patch, { received_qty: '9999999999.99' });
  assert.deepEqual(parseCell('load_type', 'fba', 1, locations).patch, { load_type: 'FBA' });
  assert.ok(parseCell('load_type', 'FBC', 1, locations).error);
  assert.ok(parseCell('memo', 'x'.repeat(4001), 1, locations).error);
});
test('paste follows visible rows and editable columns, never skips a locked row or exceeds boundaries', () => {
  const visible = [{ id: 3, editable: true }, { id: 8, editable: false }, { id: 9, editable: true }];
  assert.throws(() => pasteTargets(visible, 0, 'memo', [['one'], ['two']]));
  assert.throws(() => pasteTargets(visible, 2, 'memo', [['one'], ['two']]));
  assert.throws(() => pasteTargets(visible, 0, 'feedback', [['one', 'two']]));
  assert.throws(() => pasteTargets(visible, -1, 'memo', [['one']]));
  assert.deepEqual(pasteTargets(visible, 2, 'memo', [['note', 'feedback']]).map(x => [x.row.id, x.field, x.raw]), [[9, 'memo', 'note'], [9, 'feedback', 'feedback']]);
});
