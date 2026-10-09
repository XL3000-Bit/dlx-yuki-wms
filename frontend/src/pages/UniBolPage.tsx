import { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Alert, Breadcrumb, Button, Card, Checkbox, Dropdown, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { isAxiosError } from 'axios';
import { getCarriers, getWarehouses } from '../api/masterData';
import { actOnBol, bolStatuses, getBolLoads, getUniBol, getUniBols, saveUniBol, selectBolLoads, shippingModes, reviewBolPod, previewUniFile } from '../api/uniBol';
import type { BolLoad, UniBol, LoadQuantity, Shipout } from '../api/uniBol';
import { downloadFile } from '../api/pickingBol';
import { usePermission } from '../hooks/usePermissions';
import { PodUploadModal } from '../components/uni/PodUploadModal';
import { BolPodModal } from '../components/uni/BolPodModal';
import '../uni.css';

export const uniError = (e: unknown) => {
  const d = isAxiosError(e) ? e.response?.data?.detail : undefined;
  return typeof d === 'string' ? d : Array.isArray(d) ? d.map(x => x.msg).join('; ') : e instanceof Error ? e.message : '操作失败';
};
const stamp = (s?: string | number | null) => s ? new Date(s).toLocaleString() : '—';
const tag = (s: string) => <Tag color={['Delivered', 'Verified'].includes(s) ? 'green' : s === 'Canceled' ? 'default' : s === 'Exception' ? 'red' : 'blue'}>{s}</Tag>;
const opts = (items: string[]) => items.map(value => ({ value, label: value }));
const dateFilterOptions = [{ value: 'actual_pickup_time', label: 'Actual Pickup' }, { value: 'delivery_time', label: 'Delivery Time' }, { value: 'delivery_appointment_time', label: 'Delivery Appointment Time' }, { value: 'created_at', label: 'Created At' }];
const dateFilterDisplay = (value: string) => value ? `${value.slice(5, 7)}/${value.slice(8, 10)}/${value.slice(0, 4)}` : '';
const quantityKeys = ['carton_qty', 'pallet_qty', 'weight_lbs', 'cbm'] as const;
const available = (r: BolLoad): LoadQuantity => ({ inventory_lot_id: r.id, carton_qty: Number(r.qty ?? r.current_qty), pallet_qty: Number(r.pallets ?? r.remaining_pallets), weight_lbs: Number(r.remaining_weight_lbs ?? r.weight_lbs), cbm: Number(r.remaining_cbm ?? r.cbm) });
const requestId = () => crypto.randomUUID();
export function UniBolPage() { const { id } = useParams(); return id ? <BolDetail key={id} id={Number(id)} /> : <BolList />; }

function BolList() {
  const { message } = App.useApp(); const nav = useNavigate(); const { allowed } = usePermission('manage_outbound');
  const [filters, setFilters] = useState<Record<string, string | number | undefined>>({});
  const [q, setQ] = useState(''); const [page, setPage] = useState(1); const [size, setSize] = useState(20);
  const [more, setMore] = useState(false); const [selected, setSelected] = useState<React.Key[]>([]);
  const [dateType, setDateType] = useState('actual_pickup_time');
  const [dateFrom, setDateFrom] = useState(''); const [dateTo, setDateTo] = useState('');
  const [dateConditions, setDateConditions] = useState<{ id: string; field: string; from: string; to: string }[]>([]);
  const dates = dateConditions.map(c => JSON.stringify([c.field, dateFilterDisplay(c.from), dateFilterDisplay(c.to)]));
  const updateDateConditions = (items: typeof dateConditions) => { setDateConditions(items); setPage(1); setSelected([]); };
  const [properties, setProperties] = useState(false);
  const [podUpload, setPodUpload] = useState(false);
  const [expandedLoads, setExpandedLoads] = useState<number[]>([]);
  const [propertyEditor, setPropertyEditor] = useState(false);
  const [propertyName, setPropertyName] = useState('');
  const [propertyDraft, setPropertyDraft] = useState<string[]>([]);
  const [propertyGroups, setPropertyGroups] = useState<{ name: string; hidden: string[] }[]>(() => {
    try { return JSON.parse(localStorage.getItem('uni-bol-property-groups') || '[]'); } catch { return []; }
  });
  const [hidden, setHidden] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem('uni-bol-hidden-columns') || '[]'); } catch { return []; } });
  const change = (key: string, value?: string | number) => { setFilters(f => ({ ...f, [key]: value || undefined })); setPage(1); setSelected([]); };
  const carriers = useQuery({ queryKey: ['carriers'], queryFn: getCarriers });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses });
  const data = useQuery({ queryKey: ['uni-bols', filters, dates, page, size], queryFn: () => getUniBols({ ...filters, ...(dates.length ? { dates } : {}), page, per_page: size }), retry: false });
  const hasDateConditions = dateConditions.length > 0;
  const results = !hasDateConditions && data.isSuccess ? data.data : undefined;
  const unavailableResultsText = hasDateConditions
    ? '日期查询尚未执行，请清除日期条件后查询。'
    : data.isError ? '查询失败，请重试。' : undefined;
  const detailCol = (key: string, title: string, width = 150, date = false): ColumnsType<UniBol>[number] => ({ key, title, width, render: (_, r) => date ? (r.details[key] ? stamp(r.details[key]) : '') : r.details[key] ?? '' });
  const columns: ColumnsType<UniBol> = [
    { key: 'bol_no', title: 'BOL ID', dataIndex: 'bol_no', width: 106, render: (s, r) => <a className="uni-bol-link" href={'/outbound/bol/' + r.id} onClick={e => { e.preventDefault(); nav('/outbound/bol/' + r.id); }}>{s}</a> },
    { key: 'prev', title: 'Prev BOL#', width: 130, render: () => '' },
    { key: 'ob_no', title: 'OB#', dataIndex: 'ob_no', width: 180 }, detailCol('customer_reference', 'Customer Ref#'),
    { key: 'group_status', title: 'Group Status', dataIndex: 'group_status', width: 71 },
    { key: 'pod_status', title: 'POD Status', dataIndex: 'pod_status', width: 70 },
    { key: 'delivery_code', title: 'Delivery Code', dataIndex: 'delivery_code', width: 125 },
    { key: 'est_plt', title: 'EST PLT', width: 100, render: (_, r) => r.loads.reduce((s, l) => s + Number(l.estimate_pallets || 0), 0).toFixed(2) },
    { key: 'whs_pallets', title: 'WHS PLT', dataIndex: 'whs_pallets', width: 100, render: n => Number(n || 0).toFixed(2) },
    { key: 'operator', title: 'Operator', width: 130, render: (_, r) => r.workflow.shipouts?.at(-1)?.operator || '' },
    { key: 'created_by', title: 'Created By', dataIndex: 'created_by', width: 130 },
    { key: 'loads_count', title: 'Loads', width: 280, render: (_, r) => {
      const expanded = expandedLoads.includes(r.id);
      return <div className="uni-list-loads">{(expanded ? r.loads : r.loads.slice(0, 3)).map(l => <span key={l.id}>{l.load_id}</span>)}
        {r.loads.length > 3 && <button type="button" className="uni-text-button" onClick={() => setExpandedLoads(ids => expanded ? ids.filter(id => id !== r.id) : [...ids, r.id])}>{expanded ? 'Show Less' : `Show More (${r.loads.length - 3})`}</button>}</div>;
    } }, detailCol('shipping_mode', 'Shipping Mode', 140),
    { key: 'status', title: 'Status', dataIndex: 'status', width: 70 }, detailCol('urgent_level', 'Urgent Level', 100),
    { key: 'type', title: 'Type', dataIndex: 'type', width: 75 }, detailCol('estimated_transit_days', 'Est Transit Days', 130),
    { key: 'actual_days', title: 'Actual Transit Days', width: 145, render: () => '' },
    detailCol('payment', 'Payment', 130), detailCol('pro_number', 'Pro#', 130), detailCol('seal_number', 'Seal#', 130),
    { key: 'carrier', title: 'OTR Carrier', dataIndex: 'carrier', width: 160 }, detailCol('scheduled_pickup_time', 'Scheduled Pickup Time', 190, true),
    { key: 'actual_pickup_time', title: 'Actual Pickup Time', dataIndex: 'actual_pickup_time', width: 190, render: s => s ? stamp(s) : '' },
    { key: 'pickup', title: 'Pickup Location', dataIndex: 'pickup', width: 165 }, detailCol('pickup_reference', 'Pickup Ref#'),
    { key: 'delivery', title: 'Delivery', width: 220, render: (_, r) => r.details.delivery_address || '' }, detailCol('delivery_reference', 'Delivery Ref#'),
    detailCol('delivery_appointment', 'Delivery Appointment#', 190), detailCol('delivery_appointment_time', 'Delivery Appointment Time', 210, true),
    { title: 'Delivery Time', dataIndex: 'delivery_time', key: 'delivery_time', width: 190, render: stamp }, detailCol('remark', 'Remark', 220),
    { key: 'updated_at', title: 'Last Modified Time', dataIndex: 'updated_at', width: 190, render: stamp },
  ];
  // Widths measured from the rendered UNI list, in CSS pixels.
  const referenceWidths = [106, 65, 59, 257, 71, 70, 102, 64, 63, 89, 81, 222, 88, 70, 75, 97, 73, 73, 87, 61, 66, 74, 97, 74, 86, 74, 126, 83, 124, 116, 83, 79, 89];
  columns.forEach((column, index) => { column.width = referenceWidths[index]; });
  const selectFilter = (key: string, label: string, options: { value: string | number; label: string }[]) => <label className="uni-filter" key={key}>{label}<Select aria-label={label} allowClear value={filters[key]} options={options} onChange={v => change(key, v)} /></label>;
  const exportList = () => { if (dateConditions.length) { message.warning('日期查询规则待确认，暂不能导出此筛选结果。'); return; } const p = new URLSearchParams({ format: 'xlsx' }); Object.entries(filters).forEach(([k, v]) => { if (v !== undefined) p.set(k, String(v)); }); downloadFile('/uni-bols?' + p, 'OB-BOL.xlsx').catch(e => message.error(uniError(e))); };
  const applyProperties = (next: string[]) => { setHidden(next); localStorage.setItem('uni-bol-hidden-columns', JSON.stringify(next)); };
  const propertyMenu = <div className="uni-property-menu">
    <strong>{propertyEditor ? 'Create new property group' : 'Customized Property Group'}</strong>
    {propertyEditor ? <Input aria-label="Property group name" value={propertyName} onChange={e => setPropertyName(e.target.value)} /> : propertyGroups.length ? propertyGroups.map(g => <button type="button" className="uni-property-group" key={g.name} onClick={() => applyProperties(g.hidden)}>{g.name}</button>) : <p className="uni-muted">No Group yet</p>}
    <div className="uni-property-options">{columns.map(c => {
      const key = String(c.key), current = propertyEditor ? propertyDraft : hidden;
      const toggle = () => { const next = current.includes(key) ? current.filter(x => x !== key) : [...current, key]; propertyEditor ? setPropertyDraft(next) : applyProperties(next); };
      return <div className="uni-property-option" key={key}><button type="button" onClick={toggle}>{String(c.title)}</button><Switch size="small" aria-label={String(c.title)} checked={!current.includes(key)} onChange={toggle} /></div>;
    })}</div>
    {propertyEditor ? <Space><Button type="primary" disabled={!propertyName.trim()} onClick={() => {
      const name = propertyName.trim();
      if (propertyGroups.some(g => g.name === name)) { message.error('A property group with this name already exists'); return; }
      const next = [...propertyGroups, { name, hidden: propertyDraft }]; setPropertyGroups(next); localStorage.setItem('uni-bol-property-groups', JSON.stringify(next)); applyProperties(propertyDraft); setPropertyEditor(false);
    }}>Create</Button><Button onClick={() => setPropertyEditor(false)}>Cancel</Button></Space> : <button type="button" className="uni-text-button" onClick={() => { setPropertyName(''); setPropertyDraft(hidden); setPropertyEditor(true); }}>Create new property group</button>}
  </div>;
  return <div className="uni-page uni-bol-list"><Breadcrumb items={[{ title: 'Home' }, { title: 'Warehouse' }, { title: 'OB BOL' }]} />
    <div className="uni-list-actions"><Space size={8}>
      <Tooltip title="外部通知暂未对接"><Button disabled>POD Request</Button></Tooltip><Button onClick={exportList}>Export</Button>
      <Button disabled={!allowed} onClick={() => setPodUpload(true)}>Upload POD</Button></Space></div>
    {podUpload && <PodUploadModal onClose={() => setPodUpload(false)} />}
    <Tabs activeKey={String(filters.status || '')} onChange={s => change('status', s)} items={['', ...bolStatuses].map(key => ({ key, label: <>{key || 'All'} <span className="uni-tab-count">{results ? results.counts[key || 'All'] ?? 0 : '—'}</span></> }))} />
    <div className="uni-list-filters"><div className="uni-primary-filters">
      <label className="uni-filter uni-search-filter">Search<Input.Search aria-label="Search BOL" placeholder="for BOL#, LOAD#, CNTR#, OB#, Customer Ref#" value={q} onChange={e => setQ(e.target.value)} allowClear onSearch={s => change('q', s)} /></label>
      <label className="uni-filter uni-status-filter">BOL Status<Select aria-label="BOL Status" allowClear value={filters.status} options={opts(bolStatuses)} onChange={s => change('status', s)} /></label>
      <label className="uni-filter uni-type-filter">Type<Select aria-label="Type" allowClear value={filters.type} options={opts(['FBM', 'FBA', 'UPS', 'FedEx', 'FBA Direct', 'FBM Direct', 'Work Order', 'Other', 'Order Fulfillment', 'Temporary Storage', 'Self Pickup', 'USPS', 'DHL', 'Walmart'])} onChange={s => change('type', s)} /></label><Button type="text" className="uni-more-filters" onClick={() => setMore(!more)}>{more ? 'Hide Filters' : 'Show All Filters'}</Button>
      <div className="uni-filter-actions"><Button type="primary" onClick={() => data.refetch()}>Refresh</Button><Dropdown open={properties} onOpenChange={v => { setProperties(v); if (!v) setPropertyEditor(false); }} trigger={['click']} placement="bottomRight" popupRender={() => propertyMenu}><Button>Mange Properties</Button></Dropdown></div>
    </div>{more && <div className="uni-filter-grid">
      {selectFilter('confirmed', 'Confirmed', opts(['Yes', 'No']))}{selectFilter('shipping_mode', 'Shipping Mode', opts(shippingModes))}
      <label className="uni-filter">Creator<Input value={filters.creator || ''} onChange={e => change('creator', e.target.value)} /></label>
      {selectFilter('pod_status', 'POD Status', opts(['Not Ready', 'Awaiting Upload', 'Awaiting Verify', 'Verified', 'Exception']))}
      {selectFilter('group_status', 'Group Status', opts(['Not In WHS', 'In WHS', 'Partial In WHS', 'In Yard']))}
      <label className="uni-filter">Date Type<Select aria-label="Date Type" value={dateType} options={dateFilterOptions} onChange={setDateType} /></label>
      <label className="uni-filter">From<Input aria-label="Date From" type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></label>
      <label className="uni-filter">To<Input aria-label="Date To" type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} /></label>
      <Button onClick={() => { updateDateConditions([...dateConditions, { id: requestId(), field: dateType, from: dateFrom, to: dateTo }]); setDateFrom(''); setDateTo(''); }}>Add</Button>
      {dateConditions.length > 0 && <Space wrap style={{ gridColumn: '1 / -1' }}>
        {dateConditions.map((c, index) => <Tag key={c.id} closable closeIcon={<span aria-label={`Remove date condition ${index + 1}`}>×</span>} onClose={() => updateDateConditions(dateConditions.filter(item => item.id !== c.id))}>{dateFilterOptions.find(o => o.value === c.field)?.label}: {dateFilterDisplay(c.from)} - {dateFilterDisplay(c.to)}</Tag>)}
        <Button type="link" aria-label="Clear all date conditions" onClick={() => updateDateConditions([])}>Clear All</Button>
      </Space>}
      {selectFilter('carrier_id', 'OTR Carrier', carriers.data?.map(x => ({ value: x.id, label: x.carrier_name })) || [])}
      {selectFilter('warehouse_id', 'Pickup', warehouses.data?.map(x => ({ value: x.id, label: x.warehouse_name })) || [])}
      <label className="uni-filter">Delivery<Input value={filters.delivery_code || ''} onChange={e => change('delivery_code', e.target.value)} /></label>
      <label className="uni-filter">Customer Ref#<Input value={filters.customer_reference || ''} onChange={e => change('customer_reference', e.target.value)} /></label>
      <Button aria-label="Clear all filters" onClick={() => { setFilters({}); setQ(''); setPage(1); setSelected([]); setDateConditions([]); setDateFrom(''); setDateTo(''); setDateType('actual_pickup_time'); }}>Clear All</Button>
    </div>}</div>
    {dateConditions.length > 0 && <Alert type="warning" message="日期条件已保留；查询组合及日期边界规则待确认，尚未执行日期查询。" />}
    {data.error && <Alert type="error" message={uniError(data.error)} />}
    <Table<UniBol> size="small" bordered rowKey="id" columns={columns.filter(c => !hidden.includes(String(c.key)))} dataSource={results?.data || []} loading={data.isFetching}
      locale={unavailableResultsText ? { emptyText: unavailableResultsText } : undefined}
      rowSelection={{ selectedRowKeys: selected, onChange: setSelected, columnWidth: 44 }} scroll={{ x: referenceWidths.reduce((a, b) => a + b, 44) }}
      pagination={results ? { current: page, pageSize: size, total: results.total, pageSizeOptions: [10, 20, 50, 100], showSizeChanger: true, onChange: (p, s) => { setPage(p); setSize(s); setSelected([]); }, showTotal: n => `(${n} total)` } : false} />
  </div>;
}

function QuantityTable({ rows, values, onChange, loading }: { rows: BolLoad[]; values: Record<number, LoadQuantity>; onChange: (v: Record<number, LoadQuantity>) => void; loading?: boolean }) {
  return <Table<BolLoad> size="small" bordered rowKey="id" dataSource={rows} loading={loading} scroll={{ x: 1120 }} pagination={{ pageSize: 10 }}
    rowSelection={{ selectedRowKeys: Object.keys(values).map(Number), preserveSelectedRowKeys: true,
      onSelect: (r, selected) => { const next = { ...values }; if (selected) next[r.id] = available(r); else delete next[r.id]; onChange(next); },
      onSelectAll: (selected, _rows, changed) => { const next = { ...values }; changed.forEach(r => { if (selected) next[r.id] = available(r); else delete next[r.id]; }); onChange(next); } }}
    columns={[{ title: 'Load ID', dataIndex: 'load_id', width: 165 }, { title: 'CNTR # / Whs Marking', width: 200, render: (_, r) => <>{r.container_number}<br />{r.marking}</> },
      ...quantityKeys.map((key, i) => ({ title: ['Qty', 'WHS PLT', 'Weight LBS', 'Volume CBM'][i], width: 175, render: (_: unknown, r: BolLoad) => <div>
        <InputNumber aria-label={r.load_id + ' ' + key} min={i < 2 ? 0.01 : 0} max={available(r)[key]} precision={key === 'cbm' ? 4 : 2} disabled={!values[r.id]} value={values[r.id]?.[key]}
          onChange={v => onChange({ ...values, [r.id]: { ...values[r.id], [key]: v ?? 0 } })} style={{ width: 130 }} /><div className="uni-muted">Available: {available(r)[key]}</div></div> }))]} />;
}
function History({ rows }: { rows: Shipout[] }) {
  return <Table size="small" rowKey={r => r.request_id || r.at} pagination={false} dataSource={rows} columns={[
    { title: 'Time', dataIndex: 'at', render: stamp, width: 190 }, { title: 'Operator', dataIndex: 'operator', width: 130 },
    ...quantityKeys.map((k, i) => ({ title: ['Qty', 'PLT', 'Weight LBS', 'CBM'][i], render: (_: unknown, r: Shipout) => Number(r.lines.reduce((sum, l) => sum + Number(l[k]), 0).toFixed(4)) })),
    { title: 'Remark', dataIndex: 'remark' },
  ]} />;
}
function BolDetail({ id }: { id: number }) {
  const { modal, message } = App.useApp(); const nav = useNavigate(); const qc = useQueryClient(); const { allowed } = usePermission('manage_outbound');
  const [params, setParams] = useSearchParams(); const [form] = Form.useForm();
  const urgentLevel = Form.useWatch('urgent_level', form);
  const data = useQuery({ queryKey: ['uni-bol', id], queryFn: () => getUniBol(id), refetchOnWindowFocus: false });
  const carriers = useQuery({ queryKey: ['carriers'], queryFn: getCarriers });
  const [busy, setBusy] = useState(false); const [dirty, setDirty] = useState(false); const [select, setSelect] = useState(false);
  const [search, setSearch] = useState(''); const [quantities, setQuantities] = useState<Record<number, LoadQuantity>>({});
  const [action, setAction] = useState(''); const [checked, setChecked] = useState(false); const [remark, setRemark] = useState(''); const [request, setRequest] = useState('');
  const [podOpen, setPodOpen] = useState(false); const [review, setReview] = useState(''); const [reviewRemark, setReviewRemark] = useState('');
  const [palletCbm, setPalletCbm] = useState<number | null>(2);
  const [palletWeight, setPalletWeight] = useState<number | null>(1000);
  const [palletAlgorithm, setPalletAlgorithm] = useState('Remainder Group By Agent');
  const candidates = useQuery({ queryKey: ['uni-bol-loads', id, search], queryFn: () => getBolLoads(id, search), enabled: select });
  const row = data.data;
  useEffect(() => { if (row) { form.setFieldsValue(row.details); setDirty(false); } }, [row, form]);
  useEffect(() => { const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); }; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [dirty]);
  const commit = async (fn: () => Promise<UniBol>) => {
    setBusy(true); try { const next = await fn(); qc.setQueryData(['uni-bol', id], next);
      await Promise.all([qc.invalidateQueries({ queryKey: ['uni-bols'] }), qc.invalidateQueries({ queryKey: ['uni-bol-loads', id] }), qc.invalidateQueries({ queryKey: ['ocean-inbound'] }), qc.invalidateQueries({ queryKey: ['ocean-shipments'] })]);
      message.success('已保存'); return true;
    } catch (e) { message.error(uniError(e)); return false; } finally { setBusy(false); }
  };
  if (data.error) return <Alert type="error" message={uniError(data.error)} action={<Button onClick={() => data.refetch()}>Refresh</Button>} />;
  if (!row) return <Card loading />;
  const editable = allowed && row.status === 'Pre';
  const metadataEditable = allowed && ['In Transit', 'Delivered'].includes(row.status);
  const metadataFields = new Set(['seal_number', 'pro_number', 'payment', 'title_header', 'title_body', 'billing_to', 'remark', 'customer_remark', 'internal_remark', 'urgent_level']);
  const fieldDisabled = (key: string) => busy || !(editable || (metadataEditable && metadataFields.has(key)));
  const remaining = row.loads.filter(l => Number(l.current_qty) > 0);
  const exportUrl = (kind: string) => '/uni-bols/' + id + '/export/' + kind;
  const download = (kind: string) => downloadFile(exportUrl(kind), row.bol_no + (kind === 'labels' ? '-labels.pdf' : '.' + kind)).catch(e => message.error(uniError(e)));
  const preview = (url: string) => previewUniFile(url).catch(e => message.error(uniError(e)));
  const openAction = (a: string) => {
    if (dirty) { message.warning('请先 Save 修改，再执行状态操作'); return; }
    setChecked(false); setRemark(''); setRequest(requestId()); setAction(a);
    setQuantities(a === 'shipout' ? Object.fromEntries(remaining.map(r => [r.id, available(r)])) : {});
  };
  const save = async () => { try { const d = await form.validateFields(); await commit(() => saveUniBol(id, row.version, { ...row.details, ...d })); } catch { /* Form displays field errors. */ } };
  const textField = (key: string, label: string, max = 100) => <Form.Item key={key} name={key} label={label}><Input disabled={fieldDisabled(key)} maxLength={max} /></Form.Item>;
  const area = (key: string, label: string, max = 4000) => <Form.Item key={key} name={key} label={label}><Input.TextArea disabled={fieldDisabled(key)} rows={2} maxLength={max} /></Form.Item>;
  const dateField = (key: string, label: string) => <div className="uni-date-field"><Form.Item name={key} label={label} getValueProps={v => ({ value: v ? new Date(new Date(v).getTime() - new Date(v).getTimezoneOffset() * 60000).toISOString().slice(0, 19) : '' })} getValueFromEvent={e => e.target.value ? new Date(e.target.value).toISOString() : null}><Input disabled={fieldDisabled(key)} type="datetime-local" step={1} /></Form.Item><Button className="uni-date-now" disabled={fieldDisabled(key)} aria-label={`${label} Now`} onClick={() => { form.setFieldValue(key, new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')); setDirty(true); }}>Now</Button></div>;
  const loadNumber = (value: unknown) => Number(Number(value || 0).toFixed(4));
  const loadWeight = (value: unknown) => <span className="uni-load-weight">{Number(Number(value || 0).toFixed(2))} LBS</span>;
  const loadColumns: ColumnsType<BolLoad> = [
    { title: 'ID', dataIndex: 'load_id', width: 78 }, { title: 'Status', dataIndex: 'status', width: 56, render: tag },
    { title: 'CNTR #', dataIndex: 'container_number', width: 113 }, { title: 'Agent Code', width: 82, render: () => '—' },
    { title: 'Customer Ref #', width: 113, render: () => row.details.customer_reference || '—' },
    { title: 'Whs Marking', dataIndex: 'marking', width: 96 },
    { title: 'Receiver Shipment ID', dataIndex: 'receiver_shipment_id', width: 155 }, { title: 'Receiver Ref ID', dataIndex: 'receiver_reference_id', width: 140 },
    ...([['book_qty', 'Book Qty', 68], ['actual_qty', 'Actual Qty', 77], ['current_qty', 'Current Qty', 86]] as const).map(([dataIndex, title, width]) => ({ title, dataIndex, width, render: loadNumber })),
    { title: 'Weight', dataIndex: 'weight_lbs', width: 132, render: loadWeight },
    ...([['cbm', 'Volume CBM', 92], ['inbound_pallets', 'Inbound PLT', 123], ['whs_pallets', 'WHS PLT', 123], ['shipout_pallets', 'Shipout PLT', 88], ['remaining_pallets', 'Remaining PLT', 109], ['estimate_pallets', 'Estimate PLT', 93], ['markup_pallets', 'Markup PLT', 143]] as const).map(([dataIndex, title, width]) => ({ title, dataIndex, width, render: loadNumber })),
  ];
  const detail = <>
    <Form form={form} layout="vertical" disabled={!allowed || busy} onValuesChange={() => setDirty(true)}>
      <div className="uni-bol-detail-grid"><div className="uni-bol-pickup">
        <section className="uni-bol-section">
          <div className="uni-section-label">Pickup Notification</div>
          <Space wrap className="uni-notification-actions"><Tooltip title="外部通知对接暂缓，当前不可发送"><Button disabled>Notify OTR Carrier</Button></Tooltip><Tooltip title="外部通知对接暂缓，当前不可发送"><Button disabled>Notify Warehouse</Button></Tooltip></Space>
          <div className="uni-three-fields"><Form.Item name="shipping_mode" label="Shipping Mode"><Select disabled={fieldDisabled('shipping_mode')} options={opts(shippingModes)} /></Form.Item></div>
          <Form.Item name="carrier_id" label="OTR Carrier"><Select disabled={fieldDisabled('carrier_id')} allowClear options={carriers.data?.filter(x => x.is_active).map(x => ({ value: x.id, label: x.carrier_name }))} /></Form.Item>
        </section>
        <section className="uni-bol-section"><Button type="primary" disabled={!editable || busy || dirty} onClick={() => openAction('confirm')}>Confirm BOL</Button></section>
        <section className="uni-bol-section">
          <div className="uni-three-fields">{dateField('scheduled_pickup_time', 'Scheduled Pickup Time')}<Form.Item name="estimated_transit_days" label="Est Transit Days"><InputNumber disabled={fieldDisabled('estimated_transit_days')} min={0} max={365} precision={0} /></Form.Item></div>
          <div className="uni-location-fields"><div><Form.Item label="Pickup Location"><Input disabled value={row.pickup} /></Form.Item>{area('pickup_address', 'Pickup Address', 2000)}</div><div>{textField('pickup_reference', 'Pickup Reference')}</div></div>
        </section>
        <section className="uni-bol-section">
          <div className="uni-section-label">Actual Pickup Time</div><div className="uni-pickup-time">at {stamp(row.actual_pickup_time)}</div>
          <div className="uni-shipout-status">{row.workflow.shipouts?.length ? remaining.length ? 'Partially Shipout' : 'Fully Shipout' : ''}</div>
          <div className="uni-three-fields">{textField('seal_number', 'Seal Number')}{textField('pro_number', 'Pro Number')}</div>
          {area('customer_dispatch_remark', 'Customer Dispatch Remark')}
          <div className="uni-shipout-history"><div className="uni-history-heading">Shipout History</div>
          {(row.workflow.shipouts || []).map((shipout, index) => <div className="uni-shipout-entry" key={shipout.request_id || shipout.at}><div className="uni-shipout-caption"><strong>Shipout #{index + 1}</strong><strong>PLT {loadNumber(shipout.lines.reduce((sum, line) => sum + Number(line.pallet_qty), 0))}</strong></div><div className="uni-shipout-byline">{stamp(shipout.at)}{shipout.operator && <> by {shipout.operator}</>}</div></div>)}</div>
          <Space wrap>{!!row.workflow.shipouts?.length && <Button disabled={!allowed || busy || dirty} onClick={() => setPodOpen(true)}>Upload POD</Button>}
          {!!remaining.length && <Button type="primary" disabled={!allowed || !['Confirmed', 'In Transit'].includes(row.status) || busy || dirty} onClick={() => openAction('shipout')}>CONFIRM SIHPOUT</Button>}</Space>
        </section>
        <section className="uni-bol-section">
          <div className="uni-three-fields">{dateField('delivery_appointment_time', 'Delivery Appointment Time')}</div>
          <div className="uni-location-fields"><div><Form.Item label="Delivery Location"><Input disabled value={row.delivery_code} /></Form.Item>{area('delivery_address', 'Delivery Address', 2000)}{textField('redirect_location', 'Redirect Location', 200)}{area('redirect_address', 'Redirect Address', 2000)}</div>
            <div>{textField('delivery_appointment', 'BOL Delivery Appointment#')}{row.workflow.pod_uploads?.length ? <Form.Item label="POD Delivery Appointment#"><Input disabled value={row.workflow.pod_uploads.slice(-1)[0].delivery_appointment} /></Form.Item> : textField('pod_delivery_appointment', 'POD Delivery Appointment#')}{textField('delivery_reference', 'Delivery Reference')}</div></div>
        </section>
        <section className="uni-bol-section"><div className="uni-section-label">Delivered</div><Button disabled={!allowed || row.status !== 'In Transit' || !!remaining.length || busy || dirty} onClick={() => openAction('deliver')}>Confirm Delivery</Button>
          <div className="uni-section-label uni-delivery-history">Delivery History</div><div>{row.delivery_time ? stamp(row.delivery_time) : 'There’s no history here yet.'}</div>
        </section><div className="uni-section-label">POD {tag(row.pod_status)}</div>
      </div><section className="uni-bol-general"><strong>General Information</strong><hr /><div className="uni-form-grid">
        <Form.Item label="BOL ID"><Input disabled value={row.bol_no} /></Form.Item><Form.Item label="Type"><Input disabled value="FBA" /></Form.Item>
        <Form.Item label="Status"><Select disabled value={row.status} options={opts(bolStatuses)} /></Form.Item><Form.Item name="payment" label="Payment type" getValueFromEvent={(value) => value ?? ''}><Select disabled={fieldDisabled('payment')} allowClear options={opts(['PREPAID', 'COLLECT', 'THIRTY PAIRTY'])} /></Form.Item>
      </div><Form.Item label="Customer"><Input disabled value={row.customer} /></Form.Item>{textField('title_header', 'Title Header', 200)}
        {area('title_body', 'Title Body', 2000)}{area('billing_to', 'Billing To', 2000)}{area('remark', 'Remark (Visible on BOL)')}{area('customer_remark', 'Remark to customer (Visible on customer portal)')}{area('internal_remark', 'Internal Remark')}
        <Form.Item name="urgent_level" hidden><Input /></Form.Item>
      </section></div>
    </Form>
    <Card size="small" title="Loads" extra={row.status !== 'Delivered' ? <Button disabled={!editable || dirty || busy} onClick={() => { setQuantities({}); setSearch(''); setSelect(true); }}>Select Loads</Button> : undefined}>
      <div className="uni-pallet-bar"><label>CBM Per Pallet<InputNumber aria-label="CBM Per Pallet" value={palletCbm} onChange={setPalletCbm} /></label><label>Weight Limit Per Pallet<InputNumber aria-label="Weight Limit Per Pallet" value={palletWeight} onChange={setPalletWeight} /></label>
        <label>Algorithm<Select aria-label="Algorithm" value={palletAlgorithm} onChange={setPalletAlgorithm} options={opts(['Remainder', 'Remainder Group By Agent', 'Remainder Group By Customer'])} /></label>
        <Tooltip title="按已确认范围保留选项，暂不执行计算"><Button disabled>Calculate Pallet Count</Button></Tooltip></div>
      <div className="uni-muted">当前仅保留选项，暂不执行计算。</div>
      <Table className="uni-bol-loads" size="small" bordered rowKey="id" columns={loadColumns} dataSource={row.loads} pagination={false} scroll={{ x: 2162 }} summary={() => <Table.Summary><Table.Summary.Row>{loadColumns.map((column, index) => { const key = 'dataIndex' in column ? column.dataIndex as keyof BolLoad : undefined; const total = key ? row.loads.reduce((sum, load) => sum + Number(load[key] || 0), 0) : 0; return <Table.Summary.Cell key={index} index={index}>{index === 0 ? 'Total' : index < 8 ? '' : key === 'weight_lbs' ? loadWeight(total) : loadNumber(total)}</Table.Summary.Cell>; })}</Table.Summary.Row></Table.Summary>} />
    </Card>
    {!!row.workflow.cancellations?.length && <Card size="small" title="Cancellation History"><History rows={row.workflow.cancellations} /></Card>}
  </>;
  const documents = <Card size="small" title={<Space>POD {tag(row.pod_status)}</Space>}>
    <Button disabled={!allowed || busy || dirty || !['In Transit', 'Delivered'].includes(row.status)} onClick={() => setPodOpen(true)}>Upload POD</Button>
    <Table size="small" rowKey="id" dataSource={row.pod_documents} pagination={false} columns={[
      { title: 'File', dataIndex: 'original_filename' }, { title: 'Version', dataIndex: 'version', width: 90 },
      { title: 'Status', dataIndex: 'status', width: 140 }, { title: 'Uploaded At', dataIndex: 'created_at', render: stamp, width: 195 },
      { title: 'Actions', render: (_, d) => <Space><Button onClick={() => preview('/documents/' + d.id + '/download')}>View</Button>
        <Button onClick={() => downloadFile('/documents/' + d.id + '/download', d.original_filename).catch(e => message.error(uniError(e)))}>Download</Button>
        {d.id === row.workflow.pod_document_id && row.pod_status === 'Awaiting Verify' && <><Button disabled={!allowed || busy} onClick={() => { setReview('Verified'); setReviewRemark(''); }}>Verify</Button><Button danger disabled={!allowed || busy} onClick={() => { setReview('Exception'); setReviewRemark(''); }}>Exception</Button></>}
      </Space> },
    ]} />
    <Table size="small" rowKey={r => r.at + r.document_id} dataSource={row.workflow.pod_reviews || []} pagination={false} columns={[
      { title: 'Review Time', dataIndex: 'at', render: stamp }, { title: 'Operator', dataIndex: 'operator' }, { title: 'Result', dataIndex: 'result', render: tag }, { title: 'Remark', dataIndex: 'remark' },
    ]} />
  </Card>;
  return <div className="uni-page uni-bol-detail"><Breadcrumb items={[{ title: 'Home' }, { title: 'Warehouse' }, { title: <a onClick={() => { if (!dirty) nav('/outbound/bol'); else modal.confirm({ title: '放弃未保存的修改？', onOk: () => nav('/outbound/bol') }); }}>OB BOL</a> }, { title: row.bol_no }]} />
    <Tabs activeKey={params.get('tab') || 'detail'} onChange={tab => setParams(tab === 'detail' ? {} : { tab }, { replace: true })} items={[{ key: 'detail', label: 'Detail' }, { key: 'documents', label: 'Documents' }, { key: 'activity', label: 'Log Activities' }]} />
    <div className="uni-heading"><div><Typography.Title level={5}>BOL ID: {row.bol_no}</Typography.Title><Typography.Text type="secondary">Operator: {row.workflow.shipouts?.at(-1)?.operator || '—'} · Last Modified: {stamp(row.updated_at)}</Typography.Text></div>
      <Space wrap><Button onClick={() => preview(exportUrl('pdf'))}>View PDF</Button><Button onClick={() => download('pdf')}>Download PDF</Button><Button onClick={() => download('xlsx')}>Excel</Button><Button onClick={() => download('labels')}>Print PLT Labels</Button>
        <Dropdown disabled={fieldDisabled('urgent_level')} menu={{ items: ['No', 'Yes'].map(value => ({ key: value, label: value })), onClick: ({ key }) => { form.setFieldValue('urgent_level', key); setDirty(true); } }}><Button disabled={fieldDisabled('urgent_level')}>Urgent: {urgentLevel || row.details.urgent_level || 'No'}</Button></Dropdown>
        <Button disabled={dirty || busy} onClick={() => data.refetch()}>Refresh</Button><Button danger disabled={!allowed || !['Pre', 'Confirmed', 'In Transit'].includes(row.status) || (row.status === 'In Transit' && !remaining.length) || busy} onClick={() => openAction('cancel')}>{row.status === 'In Transit' ? 'Cancel Remaining' : 'Cancel'}</Button>
        <Button type="primary" disabled={!(editable || metadataEditable)} loading={busy} onClick={save}>Save</Button></Space></div>
    <div hidden={!!params.get('tab') && params.get('tab') !== 'detail'}>{detail}</div>
    {params.get('tab') === 'documents' && documents}
    {params.get('tab') === 'activity' && <Table size="small" rowKey={r => r.at + r.action} dataSource={row.activities} columns={[{ title: 'Action', dataIndex: 'action' }, { title: 'Time', dataIndex: 'at', render: stamp }, { title: 'Status', render: (_, r) => r.data.status }, { title: 'Version', render: (_, r) => r.data.version }]} pagination={false} />}
    {podOpen && <BolPodModal row={row} onSave={commit} onClose={() => setPodOpen(false)} />}
    <Modal title="Load Selection" width={1200} open={select} onCancel={() => !busy && setSelect(false)} okText="Select" okButtonProps={{ disabled: !Object.keys(quantities).length }} confirmLoading={busy} onOk={async () => { if (await commit(() => selectBolLoads(id, row.version, Object.values(quantities)))) setSelect(false); }}>
      <Space wrap><Input.Search placeholder="Load ID / CNTR # / Whs Marking" onSearch={setSearch} allowClear /><Tag>Type: FBA</Tag><Tag>Status: WHS Received</Tag><Tag>Delivery: {row.delivery_code}</Tag></Space>
      <Alert type="info" showIcon message="填写本单预留的实际箱数、托数、重量和体积；可拆分到不同 BOL。四项分别校验，不自动推算比例。" />
      {candidates.error && <Alert type="error" message={uniError(candidates.error)} />}
      <QuantityTable rows={candidates.data || []} values={quantities} onChange={setQuantities} loading={candidates.isFetching} />
    </Modal>
    <Modal title={action === 'shipout' ? 'CONFIRM SIHPOUT' : action === 'confirm' ? 'Confirm BOL' : action === 'deliver' ? 'Confirm Delivery' : row.status === 'In Transit' ? 'Cancel Remaining' : 'Cancel BOL'}
      width={action === 'shipout' ? 1200 : 560} open={!!action} onCancel={() => !busy && setAction('')} confirmLoading={busy}
      okButtonProps={{ disabled: action === 'shipout' && (!checked || !Object.keys(quantities).length), danger: action === 'cancel' }} onOk={async () => {
        if (await commit(() => actOnBol(id, row.version, action, { confirm_all_picked: checked, ...(action === 'shipout' ? { lines: Object.values(quantities) } : {}), request_id: request, remark }))) setAction('');
      }}>
      <p>{row.bol_no} · Remaining Qty: {row.remaining_qty} · Remaining PLT: {row.whs_pallets}</p>
      {action === 'shipout' ? <><QuantityTable rows={remaining} values={quantities} onChange={setQuantities} /><Checkbox checked={checked} onChange={e => setChecked(e.target.checked)}>已核对本次实际数量，所选货物已拣货并装车</Checkbox></>
        : <p>{action === 'confirm' ? '确认货物和承运商，生成 Picking List 和 BOL 单据。' : action === 'deliver' ? '确认本地交付完成并记录交付时间。' : '释放本单全部未发运预留。已发运数量保留，不回补已扣库存。'}</p>}
      <Form layout="vertical"><Form.Item label="Remark"><Input.TextArea maxLength={4000} value={remark} onChange={e => setRemark(e.target.value)} /></Form.Item></Form>
    </Modal>
    <Modal title={'POD · ' + review} open={!!review} onCancel={() => !busy && setReview('')} confirmLoading={busy} okButtonProps={{ disabled: review === 'Exception' && !reviewRemark.trim() }} onOk={async () => {
      if (await commit(() => reviewBolPod(id, row.version, row.workflow.pod_document_id!, review, reviewRemark))) setReview('');
    }}><p>{row.bol_no}</p><label>Remark {review === 'Exception' && '(Required)'}<Input.TextArea aria-label="POD review remark" value={reviewRemark} maxLength={4000} onChange={e => setReviewRemark(e.target.value)} /></label></Modal>
  </div>;
}

