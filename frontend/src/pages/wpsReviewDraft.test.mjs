import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createReviewDraft, restoreReviewDraft } from './wpsReviewDraft.ts';

const rows = [
  { key: 'doc:OL:1', values: { customer: '客户甲' } },
  { key: 'doc:提柜:1', values: { customer: '' } },
];
const raw = () => JSON.stringify(createReviewDraft(rows, { 'doc:OL:1': 2, 'doc:提柜:1': 3 }, 4));
test('round trip preserves both sheets, blank customer per record, warehouse', () => {
  const result = restoreReviewDraft(raw(), rows, [2, 3], [4]);
  assert.deepEqual({ ...result.overrides }, { 'doc:OL:1': 2, 'doc:提柜:1': 3 });
  assert.equal(result.warehouseId, 4);
  assert.equal(result.skipped, 0);
});
test('changed source customer, missing record, inactive customer are skipped', () => {
  const changed = [{ ...rows[0], values: { customer: '客户乙' } }, rows[1]];
  assert.equal(restoreReviewDraft(raw(), changed, [2, 3], [4]).skipped, 1);
  assert.equal(restoreReviewDraft(raw(), [], [2, 3], [4]).skipped, 2);
  assert.equal(restoreReviewDraft(raw(), rows, [2], [4]).skipped, 1);
});
test('unavailable warehouse is cleared and explicitly reported', () => {
  const result = restoreReviewDraft(raw(), rows, [2, 3], []);
  assert.equal(result.warehouseId, undefined);
  assert.equal(result.warehouseRemoved, true);
});
test('duplicate current identities cannot restore mappings', () => {
  assert.equal(restoreReviewDraft(raw(), [rows[0], rows[0]], [2, 3], [4]).skipped, 2);
  assert.throws(() => createReviewDraft([rows[0], rows[0]], {}, 4));
});
test('malformed drafts and duplicate entries are rejected', () => {
  for (const invalid of ['null', '{}', '{', JSON.stringify({ ...JSON.parse(raw()), version: 2 }),
    JSON.stringify({ ...JSON.parse(raw()), entries: [null] }),
    JSON.stringify({ ...JSON.parse(raw()), entries: [JSON.parse(raw()).entries[0], JSON.parse(raw()).entries[0]] })]) {
    assert.throws(() => restoreReviewDraft(invalid, rows, [2, 3], [4]));
  }
});
test('stale overrides cannot silently disappear during save', () => {
  assert.throws(() => createReviewDraft(rows, { 'missing:OL:99': 2 }, 4));
});
