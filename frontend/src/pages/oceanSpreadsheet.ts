import type { Receipt } from '../api/oceanInbound';

export const sheetFields = ['received_qty', 'inbound_pallets', 'location_id', 'markup_pallets', 'estimated_pallets', 'load_type', 'memo', 'feedback'] as const;
export type SheetField = typeof sheetFields[number];
export const oceanEditableFields: readonly SheetField[] = ['received_qty', 'inbound_pallets', 'location_id', 'markup_pallets', 'memo'];
export const sheetLabels: Record<SheetField, string> = { received_qty: '实收箱数', inbound_pallets: '实收托数', location_id: '库位', markup_pallets: '计费托数', estimated_pallets: '预估托数', load_type: 'Load Type', memo: '差异原因', feedback: '反馈' };
type Location = { id: number; warehouse_id: number; is_active: boolean; location_code: string };

export function parseCell(field: SheetField, raw: string, warehouse: number, locations: Location[] | undefined): { patch: Partial<Receipt>; error?: string } {
  const value = raw.trim();
  if (field === 'memo' || field === 'feedback') return raw.length > 4000 ? { patch: {}, error: '最多 4000 字' } : { patch: { [field]: raw } };
  if (!value) return { patch: { [field]: null } };
  if (field === 'location_id') {
    if (!locations) return { patch: { location_id: null }, error: '库位数据尚未加载，请稍后重试' };
    const matches = locations.filter(loc => loc.is_active && loc.warehouse_id === warehouse && loc.location_code.toLowerCase() === value.toLowerCase());
    return matches.length === 1 ? { patch: { location_id: matches[0].id } } : { patch: { location_id: null }, error: '请输入本仓有效且唯一的库位编码' };
  }
  if (field === 'load_type') return ['FBA', 'FBM'].includes(value.toUpperCase()) ? { patch: { load_type: value.toUpperCase() as 'FBA' | 'FBM' } } : { patch: {}, error: '只能填写 FBA 或 FBM' };
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(value) || Number(value) > 9999999999.99) return { patch: {}, error: '请输入非负数字，最多两位小数、十位整数' };
  return { patch: { [field]: value } };
}

// WPS/Excel clipboard TSV: quoted cells may contain tabs, newlines and escaped quotes.
export function parseSheetPaste(text: string): string[][] {
  if (text.length > 1000000) throw new Error('一次最多粘贴 1 MB 文本');
  const rows: string[][] = []; let row: string[] = []; let cell = ''; let quoted = false; let closed = false;
  const normalized = text.replace(/\r\n?/g, '\n');
  for (let i = 0; i < normalized.length; i++) {
    const ch = normalized[i];
    if (quoted) {
      if (ch === '"') { if (normalized[i + 1] === '"') { cell += '"'; i++; } else { quoted = false; closed = true; } }
      else cell += ch;
    } else if (ch === '\t' || ch === '\n') {
      row.push(cell); cell = ''; closed = false;
      if (ch === '\n') { rows.push(row); row = []; }
    } else if (closed) throw new Error('粘贴内容的引号格式不正确');
    else if (ch === '"' && !cell) quoted = true;
    else cell += ch;
  }
  if (quoted) throw new Error('粘贴内容有未闭合的引号');
  if (cell || row.length || !normalized.endsWith('\n')) { row.push(cell); rows.push(row); }
  if (rows.length > 1000) throw new Error('一次最多粘贴 1000 行');
  if (rows.some(r => r.length !== rows[0].length)) throw new Error('粘贴区域每行列数必须一致');
  return rows;
}

export function pasteTargets<T extends { editable: boolean }>(visible: T[], start: number, field: SheetField, matrix: string[][], fields: readonly SheetField[] = sheetFields) {
  const column = fields.indexOf(field);
  if (!matrix.length || !matrix[0].length || column < 0 || start < 0 || start + matrix.length > visible.length || column + matrix[0].length > fields.length) throw new Error('粘贴范围超出当前表格，请缩小区域');
  return matrix.flatMap((cells, offset) => {
    const row = visible[start + offset];
    if (!row.editable) throw new Error(`粘贴第 ${offset + 1} 行为只读，整批未修改`);
    return cells.map((raw, index) => ({ row, field: fields[column + index], raw }));
  });
}
