import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Alert, Button, Card, Descriptions, Input, Modal, Select, Space, Table, Tag, Typography, Upload } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PrinterOutlined, SaveOutlined, UploadOutlined } from '@ant-design/icons';
import { isAxiosError } from 'axios';
import { getOceanInbound, saveOceanInbound, putawayOceanInbound } from '../api/oceanInbound';
import type { OceanLine, Receipt } from '../api/oceanInbound';
import { getLocations } from '../api/masterData';
import { downloadDocument, getDocuments, uploadDocument } from '../api/documents';
import type { DocumentType } from '../api/documents';
import { receivingState } from './oceanReceivingPolicy';
import { parseCell, parseSheetPaste, pasteTargets, oceanEditableFields as sheetFields, sheetLabels } from './oceanSpreadsheet';
import type { SheetField } from './oceanSpreadsheet';
import './oceanInbound.css';

const number = (value: unknown) => Number(value ?? 0);
const display = (value: unknown) => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 });
function errorMessage(error: unknown) {
  const detail = isAxiosError(error) ? error.response?.data?.detail : undefined;
  return typeof detail === 'string' ? detail : '操作失败，请检查网络和输入后重试。';
}

export function OceanInboundPage() {
  const { modal, message } = App.useApp();
  const { id } = useParams();
  const anchorId = Number(id);
  const qc = useQueryClient();
  const queryKey = ['ocean-inbound', anchorId];
  const shipment = useQuery({ queryKey, queryFn: () => getOceanInbound(anchorId), refetchOnWindowFocus: false });
  const locations = useQuery({ queryKey: ['locations'], queryFn: getLocations });
  const [drafts, setDrafts] = useState<Record<number, Receipt>>({});
  const tableRef = useRef<HTMLDivElement>(null);
  const activeCell = useRef<{ id: number; field: SheetField } | null>(null);
  const [rawCells, setRawCells] = useState<Record<number, Partial<Record<SheetField, string>>>>({});
  const [, setSavedIds] = useState<number[]>([]);
  const [, setFailedIds] = useState<number[]>([]);
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [editingCell, setEditingCell] = useState<{ id: number; field: SheetField } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<OceanLine | null>(null);
  const [documentLine, setDocumentLine] = useState<number>();
  const [documentType, setDocumentType] = useState<DocumentType>('WAREHOUSE');
  const [uploading, setUploading] = useState(false);
  const documents = useQuery({ queryKey: ['ocean-documents', documentLine, documentType], queryFn: () => getDocuments({ inbound_id: documentLine, document_type: documentType, status: 'AVAILABLE', per_page: 100 }), enabled: !!documentLine });
  const rows = (shipment.data?.data ?? []).map(row => ({ ...row, receipt: Object.entries(rawCells[row.inbound.id] ?? {}).reduce((receipt, [field, raw]) => ({ ...receipt, ...parseCell(field as SheetField, raw, row.inbound.warehouse.id, locations.data).patch }), drafts[row.inbound.id] ?? row.receipt) }));
  const first = rows[0]?.inbound;
  const cellErrors = (row: OceanLine) => Object.entries(rawCells[row.inbound.id] ?? {}).flatMap(([field, raw]) => {
    const result = parseCell(field as SheetField, raw, row.inbound.warehouse.id, locations.data);
    return result.error ? [`${sheetLabels[field as SheetField]}：${result.error}`] : [];
  });
  const stateOf = (row: OceanLine) => {
    const state = receivingState(row, locations.data);
    const errors = cellErrors(row);
    return errors.length && row.editable ? { ...state, stage: 'pending' as const, issues: [...errors, ...state.issues] } : state;
  };
  const visible = rows;
  const selectedRows = rows.filter(row => row.editable && selected.includes(row.inbound.id));
  const dirtyRows = rows.filter(row => drafts[row.inbound.id]);
  const hasDrafts = dirtyRows.length > 0;
  useEffect(() => { setDrafts({}); setRawCells({}); setSavedIds([]); setFailedIds([]); setSelected([]); setDocumentLine(undefined); setError(''); setEditingCell(null); }, [anchorId]);
  useEffect(() => {
    if (!hasDrafts) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [hasDrafts]);
  function edit(row: OceanLine, patch: Partial<Receipt>) {
    setRawCells(current => ({ ...current, [row.inbound.id]: Object.fromEntries(Object.entries(current[row.inbound.id] ?? {}).filter(([field]) => !(field in patch))) }));
    setSavedIds(current => current.filter(id => id !== row.inbound.id));
    setFailedIds(current => current.filter(id => id !== row.inbound.id));
    setDrafts(current => ({ ...current, [row.inbound.id]: { ...(current[row.inbound.id] ?? row.receipt), ...patch } }));
  }
  function confirmSelected() {
    const blocked = selectedRows.filter(row => stateOf(row).stage !== 'ready');
    if (blocked.length) {
      modal.warning({ title: `${blocked.length} 票货物尚不能确认`, content: <div className="ocean-confirm-list">{blocked.map(row => <p key={row.inbound.id}><strong>{row.inbound.marking || row.inbound.inbound_no}</strong>：{stateOf(row).issues.join('、')}</p>)}</div> });
      return;
    }
    modal.confirm({ title: `确认 ${selectedRows.length} 票货物收货？`, okText: '确认收货', content: <><p>实收 {display(selectedRows.reduce((sum, row) => sum + number(row.receipt.received_qty), 0))} 箱 / {display(selectedRows.reduce((sum, row) => sum + number(row.receipt.inbound_pallets), 0))} 托，其中 {selectedRows.filter(row => stateOf(row).discrepancy).length} 票有数量差异。</p><p>包含当前筛选外的已选货物。确认后数量锁定；库存需在上架后生成。</p></>, onOk: () => save(selectedRows, true) });
  }
  async function save(target: OceanLine[], confirm: boolean) {
    if (!target.length || busy) return;
    const invalid = target.filter(row => cellErrors(row).length);
    if (invalid.length) { message.error(`${invalid[0].inbound.inbound_no}：${cellErrors(invalid[0]).join('；')}`); return; }
    const restore = activeCell.current;
    setBusy(true); setError('');
    try {
      const result = await saveOceanInbound(anchorId, target, confirm);
      qc.setQueryData(queryKey, result);
      setDrafts(current => Object.fromEntries(Object.entries(current).filter(([key]) => !target.some(row => row.inbound.id === Number(key)))));
      setRawCells(current => Object.fromEntries(Object.entries(current).filter(([key]) => !target.some(row => row.inbound.id === Number(key)))));
      setSavedIds(target.map(row => row.inbound.id)); setFailedIds([]);
      if (confirm) setSelected([]);
      void qc.invalidateQueries({ queryKey: ['inbound'] });
      void qc.invalidateQueries({ queryKey: ['ocean-shipments'] });
      message.success(confirm ? '已确认收货。点击 Put Away 上架生成库存。' : '收货草稿已保存');
    } catch (e) { setError(errorMessage(e)); setFailedIds(target.map(row => row.inbound.id)); if (confirm) throw e; }
    finally { setBusy(false); if (restore && !confirm) requestAnimationFrame(() => focusCell(restore.id, restore.field)); }
  }
  async function putawayReceived() {
    setBusy(true); setError('');
    try {
      const result = await putawayOceanInbound(anchorId, rows.filter(r => r.can_putaway));
      qc.setQueryData(queryKey, result);
      await Promise.all(['ocean-shipments', 'inventory', 'inbound'].map(key => qc.invalidateQueries({ queryKey: [key] })));
      message.success('Put Away 完成，库存已生成');
    } catch (e) { setError(errorMessage(e)); throw e; }
    finally { setBusy(false); }
  }
  function focusCell(id: number, field: SheetField) {
    setEditingCell({ id, field });
    requestAnimationFrame(() => {
      const input = tableRef.current?.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[data-sheet-id="${id}"][data-sheet-field="${field}"]`);
      input?.focus({ preventScroll: true }); input?.select(); input?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
  }
  function changeCell(row: OceanLine, field: SheetField, raw: string) {
    const result = parseCell(field, raw, row.inbound.warehouse.id, locations.data);
    edit(row, result.patch);
    setRawCells(current => ({ ...current, [row.inbound.id]: { ...current[row.inbound.id], [field]: raw } }));
  }
  function paste(event: React.ClipboardEvent, row: OceanLine, field: SheetField) {
    const text = event.clipboardData.getData('text/plain');
    if (!/[\t\r\n]/.test(text)) return;
    event.preventDefault();
    if (busy) return;
    try {
      const matrix = parseSheetPaste(text);
      const targets = pasteTargets(visible, visible.findIndex(r => r.inbound.id === row.inbound.id), field, matrix, sheetFields);
      const parsed = targets.map(item => ({ ...item, result: parseCell(item.field, item.raw, item.row.inbound.warehouse.id, locations.data) }));
      const invalid = parsed.find(item => item.result.error);
      if (invalid) throw new Error(`${invalid.row.inbound.inbound_no} · ${sheetLabels[invalid.field]}：${invalid.result.error}。整批未修改`);
      setDrafts(current => {
        const next = { ...current };
        for (const item of parsed) next[item.row.inbound.id] = { ...(next[item.row.inbound.id] ?? item.row.receipt), ...item.result.patch };
        return next;
      });
      setRawCells(current => {
        const next = { ...current };
        for (const item of parsed) next[item.row.inbound.id] = { ...next[item.row.inbound.id], [item.field]: item.raw };
        return next;
      });
      const ids = new Set(parsed.map(item => item.row.inbound.id));
      setSavedIds(current => current.filter(id => !ids.has(id))); setFailedIds(current => current.filter(id => !ids.has(id)));
      message.success(`已填入 ${matrix.length} 行 × ${matrix[0].length} 列，尚未保存`);
    } catch (e) { message.error(e instanceof Error ? e.message : '粘贴失败'); }
  }
  function keyDown(event: React.KeyboardEvent, row: OceanLine, field: SheetField) {
    if (event.nativeEvent.isComposing) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); void save(dirtyRows, false); return; }
    if (event.key !== 'Tab' && event.key !== 'Enter') return;
    if (event.key === 'Enter' && event.shiftKey && (field === 'memo' || field === 'feedback')) return;
    const editable = visible.filter(r => r.editable);
    const index = editable.findIndex(r => r.inbound.id === row.inbound.id);
    const col = sheetFields.indexOf(field);
    const offset = event.shiftKey ? -1 : 1;
    const next = event.key === 'Tab' ? index * sheetFields.length + col + offset : (index + offset) * sheetFields.length + col;
    if (next < 0 || next >= editable.length * sheetFields.length) { if (event.key === 'Enter') event.preventDefault(); return; }
    event.preventDefault(); focusCell(editable[Math.floor(next / sheetFields.length)].inbound.id, sheetFields[next % sheetFields.length]);
  }
  function cell(row: OceanLine, field: SheetField) {
    const location = locations.data?.find(loc => loc.id === row.receipt.location_id)?.location_code ?? row.inbound.location?.code ?? '';
    if (!row.editable) return field === 'location_id' ? location || '—' : row.receipt[field] ?? '—';
    const value = rawCells[row.inbound.id]?.[field] ?? (field === 'location_id' ? (row.receipt.location_id ? location : '') : row.receipt[field] ?? '');
    const issue = parseCell(field, String(value), row.inbound.warehouse.id, locations.data).error;
    if (editingCell?.id !== row.inbound.id || editingCell.field !== field) return <button type="button" className={`ocean-cell-value${issue ? ' has-error' : ''}`} aria-label={`${row.inbound.inbound_no} ${sheetLabels[field]}`} disabled={busy} onClick={() => focusCell(row.inbound.id, field)}>{String(value) || '\u00a0'}</button>;
    const props = {
      'aria-label': `${row.inbound.inbound_no} ${sheetLabels[field]}`,
      'aria-invalid': !!issue, 'data-sheet-id': row.inbound.id, 'data-sheet-field': field,
      value: String(value), disabled: busy, status: issue ? 'error' as const : undefined,
      autoFocus: true,
      onFocus: () => { activeCell.current = { id: row.inbound.id, field }; },
      onBlur: () => setEditingCell(current => current?.id === row.inbound.id && current.field === field ? null : current),
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => changeCell(row, field, e.target.value),
      onKeyDown: (e: React.KeyboardEvent) => keyDown(e, row, field),
      onPaste: (e: React.ClipboardEvent) => paste(e, row, field),
    };
    return <div className="ocean-sheet-cell">{field === 'memo' || field === 'feedback' ? <Input.TextArea {...props} autoSize={{ minRows: 1, maxRows: 4 }} /> : <Input {...props} list={field === 'location_id' ? `ocean-locations-${row.inbound.warehouse.id}` : field === 'load_type' ? 'ocean-load-types' : undefined} placeholder={field === 'location_id' ? '手工输入库位' : undefined} />}{issue && <span className="ocean-cell-error" role="alert">{issue}</span>}</div>;
  }
  const numeric = cell;
  const columns: ColumnsType<OceanLine> = [
    { title: 'IB Marking', width: 190, render: (_, r) => r.inbound.marking || r.inbound.inbound_no },
    { title: 'Destination', width: 110, render: (_, r) => r.inbound.fc_code || '—' },
    { title: 'Qty', width: 65, render: (_, r) => display(r.receipt.expected_qty) },
    { title: 'Unit', width: 55, render: () => '—' },
    { title: 'Weight LBS', width: 105, align: 'right', render: (_, r) => display(r.inbound.weight_lbs) },
    { title: 'CBM', width: 90, align: 'right', render: (_, r) => display(r.inbound.cbm) },
    { title: 'Received QTY', width: 120, render: (_, r) => numeric(r, 'received_qty') },
    { title: 'Inbound PLT Count', width: 120, render: (_, r) => numeric(r, 'inbound_pallets') },
    { title: 'Whs Area', width: 120, render: (_, r) => cell(r, 'location_id') },
    { title: 'WHS PLT Count', width: 95, render: (_, r) => display(r.inventory?.whs_pallets) },
    { title: 'Markup PLT Count', width: 100, render: (_, r) => numeric(r, 'markup_pallets') },
    { title: 'EST PLT Count', width: 90, render: (_, r) => display(r.receipt.estimated_pallets) },
    { title: 'Label', width: 65, render: (_, r) => <Button type="link" onClick={() => setPreview(r)}>View</Button> },
    { title: 'BOL', width: 90, render: (_, r) => r.cargo_bol_no || '—' },
    { title: 'WO', width: 65, render: () => '—' },
    { title: 'Ready To Ship', width: 95, render: () => '—' },
    { title: 'Load Type', width: 105, render: (_, r) => r.receipt.load_type || '—' },
    { title: 'Memo', width: 140, render: (_, r) => cell(r, 'memo') },
    { title: 'Carton Marking', width: 130, render: () => '' },
  ];
  function printLabel() {
    if (!preview) return;
    const popup = window.open('', '_blank', 'width=650,height=700');
    if (!popup) { message.error('请允许弹出窗口以打印标签'); return; }
    popup.opener = null;
    popup.document.title = 'Receiving Label';
    const label = popup.document.createElement('pre');
    label.style.cssText = 'font:20px/1.8 sans-serif;white-space:pre-wrap;border:2px solid;padding:24px';
    label.textContent = `RECEIVING LABEL\n${preview.inbound.container_number}\n${preview.inbound.marking || preview.inbound.inbound_no}\nDestination: ${preview.inbound.fc_code || '—'}\nCargo BOL: ${preview.cargo_bol_no || '—'}\nInbound: ${preview.inbound.inbound_no}\nReceived cartons: ${preview.receipt.received_qty ?? '—'}\nPallets: ${preview.receipt.inbound_pallets ?? '—'}\n${preview.receipt.confirmed_date ? 'Confirmed: ' + preview.receipt.confirmed_date : 'Status: ' + preview.inbound.status_name}`;
    popup.document.body.append(label); popup.focus(); popup.print();
  }
  return <div className="page ocean-page ocean-detail">
    <div className="ocean-shipment-heading">
      <div><div className="ocean-shipment-reference">{first?.container_number || '—'} / {first?.inbound_no || '—'} / / / {first?.unload_date || ''} / {shipment.data?.shipment.operator || ''} / {shipment.data?.shipment.team || ''}</div><div className="ocean-shipment-caption"># IB Shipment / # WHS Alert / # Pieces / Size / OP / Unloading Team</div></div>
      <Space><Button type="primary" disabled={!selectedRows.length || busy} onClick={confirmSelected}>CONFIRM RECEIVED</Button></Space>
    </div>
    <Typography.Title level={4}>Ocean Transload Shipment Inbound (by Loads)</Typography.Title>
    {(error || shipment.isError) && <Alert type="error" showIcon message={error || errorMessage(shipment.error)} action={<Button onClick={() => modal.confirm({ title: '重新加载将放弃未保存的修改，继续？', onOk: async () => { setDrafts({}); setRawCells({}); setSavedIds([]); setFailedIds([]); setSelected([]); setError(''); await shipment.refetch(); } })}>重新加载</Button>} />}
    {Array.from(new Set(rows.map(row => row.inbound.warehouse.id))).map(warehouse => <datalist key={warehouse} id={`ocean-locations-${warehouse}`}>{(locations.data ?? []).filter(loc => loc.warehouse_id === warehouse && loc.is_active).map(loc => <option key={loc.id} value={loc.location_code} />)}</datalist>)}
    <datalist id="ocean-load-types"><option value="FBA" /><option value="FBM" /></datalist>
    <div ref={tableRef} className="ocean-sheet"><Table<OceanLine> className="dense-table" tableLayout="fixed" rowKey={r => r.inbound.id} loading={shipment.isLoading} dataSource={visible} columns={columns} scroll={{ x: 2100 }} pagination={false} rowSelection={{ columnWidth: 40, selectedRowKeys: selected, preserveSelectedRowKeys: true, onChange: setSelected, getCheckboxProps: () => ({ disabled: busy }) }} summary={data => {
      const totals: Record<number, number> = {
        3: data.reduce((s, r) => s + number(r.receipt.expected_qty), 0),
        5: data.reduce((s, r) => s + number(r.inbound.weight_lbs), 0),
        6: data.reduce((s, r) => s + number(r.inbound.cbm), 0),
        7: data.reduce((s, r) => s + number(r.receipt.received_qty), 0),
        8: data.reduce((s, r) => s + number(r.receipt.inbound_pallets), 0),
        10: data.reduce((s, r) => s + number(r.inventory?.whs_pallets), 0),
        11: data.reduce((s, r) => s + number(r.receipt.markup_pallets), 0),
        12: data.reduce((s, r) => s + number(r.receipt.estimated_pallets), 0),
      };
      return <Table.Summary.Row>{Array.from({ length: 20 }, (_, index) => <Table.Summary.Cell key={index} index={index}>{index === 1 ? 'Total' : index in totals ? display(totals[index]) : ''}</Table.Summary.Cell>)}</Table.Summary.Row>;
    }} /></div>
    <div className="ocean-pending-controls"><Button icon={<SaveOutlined />} disabled={!hasDrafts || busy} loading={busy} onClick={() => save(dirtyRows, false)}>保存草稿{hasDrafts ? ` (${dirtyRows.length})` : ''}</Button><Button disabled={hasDrafts || busy || !rows.some(r => r.can_putaway)} onClick={() => modal.confirm({ title: 'Put Away · 上架生成库存', content: `为 ${rows.filter(r => r.can_putaway).length} 票已收货货物生成库存。确认收货数量与库位正确后继续。`, onOk: putawayReceived })}>Put Away ({rows.filter(r => r.can_putaway).length})</Button><span>现有本地收货操作；与 UNI Sync 的对应规则待确认。</span></div>
    <Card title="入库附件" className="ocean-documents"><Space wrap><Select placeholder="选择附件所属货物" style={{ width: 280 }} value={documentLine} onChange={setDocumentLine} options={rows.map(r => ({ value: r.inbound.id, label: `${r.inbound.inbound_no} · ${r.inbound.marking || r.inbound.fc_code || '—'}` }))} /><Select value={documentType} onChange={setDocumentType} style={{ width: 200 }} options={[{ value: 'WAREHOUSE', label: 'WHS File · 仓库文件' }, { value: 'GENERAL', label: 'Admin Document · 管理文件' }]} /><Upload showUploadList={false} accept=".pdf,.xlsx,.xls,.csv,.jpg,.jpeg,.png" disabled={!documentLine || uploading || !shipment.data?.can_upload} beforeUpload={file => { setUploading(true); uploadDocument({ inbound_id: documentLine, document_type: documentType }, file).then(() => { message.success('附件已保存'); void documents.refetch(); }).catch(e => message.error(errorMessage(e))).finally(() => setUploading(false)); return false; }}><Button icon={<UploadOutlined />} disabled={!documentLine || !shipment.data?.can_upload} loading={uploading}>上传文件</Button></Upload></Space><p className="ocean-subtle">仓库文件保留版本；管理文件可多份并存。PDF / Excel / CSV / JPG / PNG。附件按所选货物的客户、仓库权限保存。</p>{documents.isError && <Alert type="error" message={errorMessage(documents.error)} />}<Space direction="vertical">{documents.data?.data.map(doc => <Button key={doc.id} type="link" onClick={() => downloadDocument(doc).catch(e => message.error(errorMessage(e)))}>{doc.original_filename} · v{doc.version}</Button>)}{documentLine && !documents.isLoading && !documents.data?.data.length && <Typography.Text type="secondary">暂无附件</Typography.Text>}</Space></Card>
    <Modal open={!!preview} title="Receiving Label / Cargo BOL" onCancel={() => setPreview(null)} footer={<Button icon={<PrinterOutlined />} onClick={printLabel}>打印收货标签</Button>}>
      {preview && <><Tag color={preview.receipt.confirmed_date ? 'green' : 'orange'}>{preview.receipt.confirmed_date ? '已确认收货' : preview.inbound.status_name}</Tag><Descriptions column={1} bordered size="small" items={[
        { key: 'container', label: 'Container', children: preview.inbound.container_number }, { key: 'ib', label: 'Inbound', children: preview.inbound.inbound_no }, { key: 'marking', label: 'Marking', children: preview.inbound.marking || '—' }, { key: 'destination', label: 'Destination', children: preview.inbound.fc_code || '—' }, { key: 'bol', label: 'Cargo BOL', children: preview.cargo_bol_no || '—' }, { key: 'qty', label: '实收箱数 / 托数', children: `${display(preview.receipt.received_qty)} / ${display(preview.receipt.inbound_pallets)}` },
      ]} /><p className="ocean-subtle">用于仓库收货识别。运输 BOL 请通过现有出库 BOL 流程生成。</p></>}
    </Modal>
  </div>;
}
