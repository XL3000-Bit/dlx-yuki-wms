import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { App, Alert, Button, Form, Input, Select, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { getOceanShipments, saveOceanShipment, transportStatuses } from '../api/oceanInbound';
import type { OceanListRow, ShipmentMetadata } from '../api/oceanInbound';
import { usePermission } from '../hooks/usePermissions';
import { uniError } from './UniBolPage';
import '../uni.css';

const listStatuses = ['Upcoming Inbound', "Today's Inbound", 'Overdue Inbound', 'Completed Inbound', 'Canceled Inbound'];
const yesNo = [{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }];
const dateText = (value?: string | null, empty = 'TBD') => value ? <span className="ocean-date">{value.replace('T', ' ').replace(/(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/, '').split(' ').map((part, i) => <span key={i}>{part}</span>)}</span> : empty;
const bilingual = (title: string, subtitle: string) => <span className="ocean-bilingual">{title}<small>{subtitle}</small></span>;

function RemarkCell({ value, disabled, save }: { value: string; disabled: boolean; save: (value: string) => Promise<boolean> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const submitting = useRef(false);
  useEffect(() => { setDraft(value); }, [value]);
  const commit = async () => {
    if (submitting.current) return;
    if (draft === value) { setEditing(false); return; }
    submitting.current = true;
    if (await save(draft)) setEditing(false);
    submitting.current = false;
  };
  return editing ? <Input autoFocus aria-label="Unloading Remark" value={draft} maxLength={1024} disabled={disabled}
    onChange={e => setDraft(e.target.value)} onBlur={commit} onPressEnter={e => e.currentTarget.blur()}
    onKeyDown={e => { if (e.key === 'Escape') { setDraft(value); setEditing(false); } }} />
    : <button className="ocean-remark" disabled={disabled} onClick={() => setEditing(true)}>{value || 'TBD'}</button>;
}

export function OceanInboundListPage() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const { allowed } = usePermission('manage_inbound');
  const [form] = Form.useForm();
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState<Set<number>>(new Set());
  const pending = useRef(new Set<number>());
  const rows = useInfiniteQuery({ queryKey: ['ocean-shipments', params], initialPageParam: 1,
    queryFn: ({ pageParam }) => getOceanShipments({ ...params, page: pageParam, per_page: 20 }),
    getNextPageParam: (last, pages) => pages.reduce((n, p) => n + p.data.length, 0) < last.total ? pages.length + 1 : undefined,
  });
  const first = rows.data?.pages[0];
  const data = rows.data?.pages.flatMap(p => p.data) || [];
  const save = async (row: OceanListRow, patch: Partial<ShipmentMetadata>) => {
    if (pending.current.has(row.id)) return false;
    pending.current.add(row.id); setSaving(new Set(pending.current));
    try {
      await saveOceanShipment(row.id, { ...patch, version: row.shipment.version });
      await Promise.all([qc.invalidateQueries({ queryKey: ['ocean-shipments'] }), qc.invalidateQueries({ queryKey: ['ocean-inbound', row.id] })]);
      return true;
    } catch (error) { message.error(uniError(error)); await rows.refetch(); return false; }
    finally { pending.current.delete(row.id); setSaving(new Set(pending.current)); }
  };
  const binaryCell = (key: 'printed' | 'empty_reported', label: string, row: OceanListRow) => <select aria-label={`${label} ${row.container_number}`}
    className="ocean-inline-select ocean-binary" disabled={!allowed || saving.has(row.id)} value={String(!!row.shipment[key])}
    onChange={e => void save(row, { [key]: e.target.value === 'true' })}><option value="true">Yes</option><option value="false">No</option></select>;
  const columns: ColumnsType<OceanListRow> = ([
    { title: 'Container Number', width: 215, render: (_, r) => <div className="ocean-container"><Link to={`/inbound/ocean/${r.id}`}>{r.container_number}</Link><Link className="ocean-new" to={`/inbound/ocean/${r.id}`} target="_blank" rel="noreferrer">NEW</Link></div> },
    { title: 'POD ETA', width: 62, render: (_, r) => dateText(r.shipment.pod_eta) },
    { title: 'IR ETA', width: 61, render: (_, r) => dateText(r.shipment.ir_eta) },
    { title: 'Urgent', width: 43, render: (_, r) => r.shipment.urgent ? <span className="ocean-urgent">Yes</span> : '' },
    { title: 'Release Status', width: 82, render: (_, r) => <span className={`ocean-release ${r.shipment.released ? 'released' : 'hold'}`}>{r.shipment.released ? 'Released' : 'Hold'}</span> },
    { title: 'Trouble Status', width: 79, render: (_, r) => <div>{r.shipment.trouble_status || '-'}{!!r.shipment.trouble_count && <><br /><span>+{r.shipment.trouble_count}</span></>}</div> },
    { title: 'Term. Ready Date', width: 101, render: (_, r) => dateText(r.shipment.terminal_ready_date, '') },
    { title: bilingual('Apt', '提柜时间'), width: 106, render: (_, r) => dateText(r.shipment.appointment, '') },
    { title: bilingual('Trucker', '提柜车队'), width: 145, render: (_, r) => r.shipment.trucker || '-' },
    { title: bilingual('Container Status', '货柜状态'), width: 150, render: (_, r) => <select aria-label={`Container Status ${r.container_number}`} className="ocean-inline-select"
      disabled={!allowed || saving.has(r.id)} value={r.shipment.transport_status || 'TBD'} onChange={e => void save(r, { transport_status: e.target.value })}>
      {transportStatuses.map(s => <option key={s} value={s} disabled={s === 'TBD'} hidden={s === 'TBD'}>{s === 'TBD' ? '' : s}</option>)}</select> },
    { title: 'Printed', width: 100, render: (_, r) => binaryCell('printed', 'Printed', r) },
    { title: 'Empty Reported', width: 120, render: (_, r) => binaryCell('empty_reported', 'Empty Reported', r) },
    { title: bilingual('Unloading Date', '拆柜日期'), width: 150, render: (_, r) => dateText(r.unload_date) },
    { title: bilingual('Unloading Team', '拆柜团队'), width: 180, render: (_, r) => r.shipment.team || 'TBD' },
    { title: bilingual('Unloading Amount', '拆柜金额'), width: 120, render: (_, r) => r.shipment.unloading_amount == null ? 'TBD' : Number(r.shipment.unloading_amount).toFixed(2) },
    { title: bilingual('Unloading Remark', '仓库备注'), width: 180, render: (_, r) => <RemarkCell value={r.shipment.unloading_remark || ''} disabled={!allowed || saving.has(r.id)} save={value => save(r, { unloading_remark: value })} /> },
    { title: 'Scheduled Delivery Date', width: 139, render: (_, r) => dateText(r.shipment.scheduled_delivery_date) },
    { title: 'Status', width: 87, render: (_, r) => r.shipment.list_status || '-' },
    { title: 'Number of Piece', dataIndex: 'pieces', width: 89, render: v => Number(v).toFixed(2) },
    { title: 'Container Size', width: 83, render: (_, r) => r.shipment.size || 'TBD' },
    { title: 'OP', width: 35, render: (_, r) => r.shipment.operator || '-' },
    { title: '', width: 16, render: () => null },
  ] satisfies ColumnsType<OceanListRow>).map(c => ({ ...c, align: 'center' as const }));
  const apply = (values: Record<string, unknown>) => setParams(Object.fromEntries(Object.entries(values)
    .map(([k, v]) => [k, Array.isArray(v) ? v.join('|') : v]).filter(([, v]) => v !== '' && v != null)));
  const multi = (name: string, options: string[]) => <Form.Item name={name} noStyle><Select mode="multiple" allowClear placeholder="All" options={options.map(value => ({ value, label: value }))} /></Form.Item>;
  const binary = (name: string, options = yesNo) => <Form.Item name={name} noStyle><Select allowClear placeholder="All" options={options} /></Form.Item>;
  const range = (from: string, to: string, label: string) => <div className="ocean-date-range"><Form.Item name={from} noStyle><Input aria-label={`${label} from`} type="date" /></Form.Item><span>~</span><Form.Item name={to} noStyle><Input aria-label={`${label} to`} type="date" /></Form.Item></div>;
  return <div className="uni-page uni-ocean-list">
    <Form form={form} onFinish={apply} className="ocean-filters">
      <label className="uni-filter">Container Number<Form.Item name="q" noStyle><Input placeholder="Search..." allowClear /></Form.Item></label>
      <div className="uni-filter">Scheduled Delivery Date{range('scheduled_from', 'scheduled_to', 'Scheduled Delivery Date')}</div>
      <div className="uni-filter">Printed{binary('printed')}</div>
      <div className="uni-filter">Empty Reported{binary('empty_reported')}</div>
      <div className="uni-filter">Unloading Date / 拆柜日期{range('date_from', 'date_to', 'Unloading Date')}</div>
      <div className="uni-filter">Status{multi('list_status', listStatuses)}</div>
      <div className="uni-filter">Release Status{binary('released', [{ value: 'true', label: 'Released' }, { value: 'false', label: 'Hold' }])}</div>
      <div className="uni-filter">CNTR Size{multi('size', first?.options.size || [])}</div>
      <div className="uni-filter">Trucker / 提柜车队{multi('trucker', first?.options.trucker || [])}</div>
      <div className="uni-filter">Container Status / 货柜状态{multi('transport_status', transportStatuses.slice(1))}</div>
      <div className="uni-filter">Unloading Team / 拆柜团队<Form.Item name="team" noStyle><Select showSearch allowClear placeholder="Search..." options={(first?.options.team || []).map(value => ({ value, label: value }))} /></Form.Item></div>
      <div className="uni-filter">Outbound Fully POD{binary('outbound_fully_pod')}</div>
      <div className="uni-filter">POD ETA{range('pod_eta_from', 'pod_eta_to', 'POD ETA')}</div>
      <div className="uni-filter">Apt / 提柜时间{range('appointment_from', 'appointment_to', 'Apt')}</div>
      <div className="ocean-filter-actions"><Button type="primary" htmlType="submit">Apply</Button><Button onClick={() => { form.resetFields(); setParams({}); }}>Reset Filter</Button></div>
    </Form>
    <div className="ocean-counts">{['Total', ...listStatuses].map(status => <button key={status} className={(status === 'Total' ? !params.list_status : params.list_status === status) ? 'active' : ''}
      onClick={() => { const value = status === 'Total' ? undefined : status; form.setFieldValue('list_status', value ? [value] : []); setParams(current => ({ ...current, list_status: value })); }}>
      <span>{status}</span><strong>{first?.counts[status] || 0}</strong></button>)}</div>
    {rows.error && <Alert type="error" showIcon message={uniError(rows.error)} />}
    <Table rowKey="id" className="ocean-list-table" loading={rows.isFetching && !rows.isFetchingNextPage} dataSource={data} columns={columns} pagination={false} scroll={{ x: 2543 }} />
    <div className="ocean-show-more"><Button disabled={!rows.hasNextPage} loading={rows.isFetchingNextPage} onClick={() => void rows.fetchNextPage()}>Show More</Button></div>
  </div>;
}
