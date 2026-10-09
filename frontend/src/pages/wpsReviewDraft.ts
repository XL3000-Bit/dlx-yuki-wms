export interface DraftRow { key: string; values: Record<string, unknown> }
interface DraftEntry { key: string; customerId: number; sourceCustomer: string }
export interface ReviewDraft { version: 1; savedAt: string; warehouseId: number | null; entries: DraftEntry[] }
const sourceCustomer = (row: DraftRow) => JSON.stringify(row.values.customer ?? null);
const validId = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;

export function createReviewDraft(rows: DraftRow[], overrides: Record<string, number>, warehouseId?: number): ReviewDraft {
  const entries: DraftEntry[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    if (seen.has(row.key)) throw new Error('样本包含重复来源标识，不能保存草稿。');
    seen.add(row.key);
    if (Object.hasOwn(overrides, row.key)) {
      const customerId = overrides[row.key];
      if (!validId(customerId)) throw new Error('客户映射无效。');
      entries.push({ key: row.key, customerId, sourceCustomer: sourceCustomer(row) });
    }
  }
  if (entries.length !== Object.keys(overrides).length) throw new Error('部分映射的来源记录已不在样本中，请清除后重新核对。');
  return { version: 1, savedAt: new Date().toISOString(), warehouseId: warehouseId ?? null, entries };
}

export function restoreReviewDraft(raw: string, rows: DraftRow[], customerIds: number[], warehouseIds: number[]) {
  const draft: unknown = JSON.parse(raw);
  if (!draft || typeof draft !== 'object') throw new Error('草稿格式无效。');
  const d = draft as ReviewDraft;
  if (d.version !== 1 || typeof d.savedAt !== 'string' || !Number.isFinite(Date.parse(d.savedAt)) ||
      (d.warehouseId !== null && !validId(d.warehouseId)) || !Array.isArray(d.entries) || d.entries.length > 10000) {
    throw new Error('草稿版本或格式无效。');
  }
  const byKey = new Map<string, DraftRow>();
  const duplicates = new Set<string>();
  for (const row of rows) {
    if (byKey.has(row.key)) duplicates.add(row.key);
    byKey.set(row.key, row);
  }
  const activeCustomers = new Set(customerIds);
  const overrides: Record<string, number> = Object.create(null);
  const seen = new Set<string>();
  let skipped = 0;
  for (const entry of d.entries) {
    if (!entry || typeof entry.key !== 'string' || !validId(entry.customerId) || typeof entry.sourceCustomer !== 'string' || seen.has(entry.key)) {
      throw new Error('草稿客户映射格式无效或来源重复。');
    }
    seen.add(entry.key);
    const row = byKey.get(entry.key);
    if (!row || duplicates.has(entry.key) || sourceCustomer(row) !== entry.sourceCustomer || !activeCustomers.has(entry.customerId)) {
      skipped++;
      continue;
    }
    overrides[entry.key] = entry.customerId;
  }
  const warehouseRemoved = d.warehouseId !== null && !warehouseIds.includes(d.warehouseId);
  return { overrides, skipped, warehouseId: warehouseRemoved ? undefined : d.warehouseId ?? undefined, warehouseRemoved, savedAt: d.savedAt };
}
