// Paste into WPS AirScript. Reads business fields only; never updates records.
// JSON round-trip materializes WPS proxy values before using array operations.
const plain = value => JSON.parse(JSON.stringify(value));
const args = typeof Context !== "undefined" && Context.argv ? Context.argv : {};
const fieldsBySheet = {
  "提柜": ["柜号", "客户", "船司", "MBL", "状态", "ETA", "柜型", "件数", "预计到仓时间", "实际到仓日期", "完成拆柜日期", "备注"],
  "OL": ["柜号", "仓点", "库位", "板数", "件数", "磅数(lb)", "重量(kg)", "体积", "客户", "拆柜时间", "实际到仓时间", "FBA", "PO", "备注", "库位更新时间"],
  "DS": ["客户", "柜号", "ID", "FBA", "PO", "件数", "LBS", "体积", "派送仓点", "备注", "关联OL"],
  "出库": ["计划单号", "单号-仓点", "仓点", "ISA/预约编号", "预计送仓时间", "出库时间", "真实板数", "预计体积", "预计板数", "重量(lb)", "预计重量", "车队", "Redirect Code", "预计件数", "PO", "FBA", "计划出库"]
};
const name = args.sheet || "提柜";
if (!Object.prototype.hasOwnProperty.call(fieldsBySheet, name)) throw new Error("Unsupported sheet");
const pageSize = args.pageSize === undefined ? 20 : Number(args.pageSize);
if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) throw new Error("pageSize must be 1..100");
if (args.offset !== undefined && typeof args.offset !== "string") throw new Error("Invalid offset");
const sheets = plain(Application.Sheet.GetSheets());
const sheet = sheets.find(item => item.name === name);
if (!sheet) throw new Error("Sheet not found: " + name);
const available = sheet.fields.map(field => field.name);
const fields = fieldsBySheet[name].filter(field => available.includes(field));
const page = plain(Application.Record.GetRecords({
  SheetId: sheet.id, PageSize: pageSize, Offset: args.offset || "", Fields: fields
}));
const output = {
  schemaVersion: 1, mode: "read_only", sheet: {id: sheet.id, name: sheet.name},
  fields: fields, missingFields: fieldsBySheet[name].filter(field => !available.includes(field)),
  records: page.records || [], nextOffset: page.offset || null
};
console.log(JSON.stringify({mode:output.mode, sheet:name, count:output.records.length,
  hasMore:!!output.nextOffset, missingFields:output.missingFields}));
return output;
