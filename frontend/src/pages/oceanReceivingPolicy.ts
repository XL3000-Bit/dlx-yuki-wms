import type { OceanLine, Receipt } from '../api/oceanInbound';

type ReceivingLocation = { id: number; warehouse_id: number; is_active: boolean };
export type ReceivingStage = 'all' | 'pending' | 'ready' | 'received' | 'readonly' | 'discrepancy';

function validQuantity(value: unknown): boolean {
  return value !== null && value !== undefined && String(value).trim() !== '' &&
    Number.isFinite(Number(value)) && Number(value) >= 0;
}

export function receivingState(row: OceanLine, locations: ReceivingLocation[] | undefined) {
  const receipt = row.receipt;
  const discrepancy = validQuantity(receipt.received_qty) && Number(receipt.received_qty) !== Number(receipt.expected_qty);
  const issues: string[] = [];
  if (!validQuantity(receipt.received_qty)) issues.push('填写实收箱数');
  if (!validQuantity(receipt.inbound_pallets)) issues.push('填写实收托数');
  if (!receipt.location_id) issues.push('选择库位');
  else if (!locations) issues.push('等待库位校验');
  else if (!locations.some(loc => loc.id === receipt.location_id && loc.warehouse_id === row.inbound.warehouse.id && loc.is_active)) issues.push('选择本仓有效库位');
  if (discrepancy && !receipt.memo?.trim()) issues.push('填写箱数差异原因');
  const stage: ReceivingStage = row.editable ? (issues.length ? 'pending' : 'ready') :
    (receipt.confirmed_date || [2, 3, 4].includes(row.inbound.status) ? 'received' : 'readonly');
  return { stage, issues, discrepancy, delta: discrepancy ? Number(receipt.received_qty) - Number(receipt.expected_qty) : 0 };
}

export function fillMissingExpected(receipt: Receipt): Partial<Receipt> {
  const patch: Partial<Receipt> = {};
  if (receipt.received_qty == null || receipt.received_qty === '') patch.received_qty = receipt.expected_qty;
  if (receipt.inbound_pallets == null || receipt.inbound_pallets === '') patch.inbound_pallets = receipt.expected_pallets;
  return patch;
}
