import { SettingOutlined, WarningOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'
import { Button, Checkbox, Space, Table, Tag, Tooltip } from 'antd'
import { useState } from 'react'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { FBAWorkbenchRow } from '../../types/fbaWorkbench'
import { DispatchPriorityTag, OutboundDateCell } from '../DispatchIndicators'
export interface ColumnPreference { key: string; visible: boolean; width: number }
const num = (v: string, d = 0) => Number(v).toLocaleString(undefined, { maximumFractionDigits: d }); const colors: Record<string, string> = { RED: 'red', ORANGE: 'orange', YELLOW: 'gold', GREEN: 'green' }
export const defaultColumns: ColumnPreference[] = [['dispatch_priority',90],['earliest_outbound_date',100],['outbound_days_remaining',80],['priority_level',95],['max_aging_days',75],['oldest_inbound_date',100],['fba_no',135],['st_number',115],['containers_preview',125],['amazon_fc_code',75],['locations_preview',115],['total_pallet_qty',82],['total_carton_qty',82],['total_weight_lbs',95],['total_cbm',75],['appointment_time',130],['picking_no',110],['bol_no',105],['workbench_stage_name',90]].map(([key,width]) => ({ key: String(key), width: Number(width), visible: true }))
export function FBAWorkbenchTable({ rows, loading, selected, onSelected, onOpen, page, per, total, onPage, onSort, preferences, onPreferences }: { rows: FBAWorkbenchRow[]; loading: boolean; selected: number[]; onSelected: (ids: number[]) => void; onOpen: (row: FBAWorkbenchRow) => void; page: number; per: number; total: number; onPage: (p: TablePaginationConfig) => void; onSort: (field: string, order: 'asc' | 'desc') => void; preferences: ColumnPreference[]; onPreferences: (p: ColumnPreference[]) => void }) {
  const [propertiesOpen, setPropertiesOpen] = useState(false)
  const defs: Record<string, ColumnsType<FBAWorkbenchRow>[number]> = { priority_level: { title: 'Priority', dataIndex: 'priority_level', sorter: true, render: (_, r) => r.priority_level ? <Tooltip title={`${r.priority_label} (${r.priority_range})`}><Tag color={colors[r.priority_level]}>{r.priority_label}</Tag></Tooltip> : '-' }, max_aging_days: { title: 'Aging Days', dataIndex: 'max_aging_days', sorter: true }, oldest_inbound_date: { title: 'Oldest Inbound', dataIndex: 'oldest_inbound_date', sorter: true }, fba_no: { title: 'FBA No', dataIndex: 'fba_no', sorter: true, render: (v, r) => <Button type="link" onClick={() => onOpen(r)}>{v}</Button> }, st_number: { title: 'ST Number', dataIndex: 'st_number', sorter: true }, containers_preview: { title: 'Container', render: (_, r) => <Tooltip title={r.containers_preview.join('\n')}>{r.container_count === 1 ? r.containers_preview[0] || '-' : `${r.container_count} Containers`}</Tooltip> }, amazon_fc_code: { title: 'FC', dataIndex: 'amazon_fc_code', sorter: true, render: (v, r) => <span>{v} {r.fc_address_missing && <WarningOutlined className="fc-warning" />}</span> }, locations_preview: { title: 'Location', render: (_, r) => <Tooltip title={r.locations_preview.join('\n')}>{r.location_count <= 1 ? r.locations_preview[0] || '-' : `${r.location_count} Locations`}</Tooltip> }, total_pallet_qty: { title: 'Pallet', dataIndex: 'total_pallet_qty', sorter: true, render: v => num(v, 2) }, total_carton_qty: { title: 'Carton', dataIndex: 'total_carton_qty', sorter: true, render: v => num(v) }, total_weight_lbs: { title: 'Weight LB', dataIndex: 'total_weight_lbs', sorter: true, render: v => num(v) }, total_cbm: { title: 'CBM', dataIndex: 'total_cbm', sorter: true, render: v => num(v, 2) }, appointment_time: { title: 'Appointment', dataIndex: 'appointment_time', sorter: true, render: v => v ? new Date(v).toLocaleString('en-US') : '-' }, picking_no: { title: 'Picking', dataIndex: 'picking_no', render: v => v || '-' }, bol_no: { title: 'BOL', dataIndex: 'bol_no', render: v => v || '-' }, workbench_stage_name: { title: 'Stage', dataIndex: 'workbench_stage_name', render: (v, r) => <Tag color={r.has_exception ? 'red' : r.workbench_stage === 'completed' ? 'green' : 'orange'}>{v}</Tag> } }
  Object.assign(defs, { dispatch_priority: { title: 'Dispatch', dataIndex: 'dispatch_priority', sorter: true, render: (v: string) => <DispatchPriorityTag value={v} /> }, earliest_outbound_date: { title: 'Earliest OB', dataIndex: 'earliest_outbound_date', sorter: true, render: (v: string, r: FBAWorkbenchRow) => <OutboundDateCell value={v} days={r.outbound_days_remaining} /> }, outbound_days_remaining: { title: 'Days Left', dataIndex: 'outbound_days_remaining', sorter: true, render: (v: number | null) => v ?? '-' } })
  const known = preferences.filter(p => defs[p.key])
  const columns = known.filter(p => p.visible).map(p => ({ ...defs[p.key], key: p.key, width: Math.max(p.width, 110) }))
  const moveColumn = (index: number, offset: number) => {
    const next = [...known]
    const target = index + offset
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    onPreferences(next)
  }
  return <div className="workbench-table">
    <div className="fba-properties-toolbar"><Button icon={<SettingOutlined />} aria-expanded={propertiesOpen} onClick={() => setPropertiesOpen(!propertiesOpen)}>Manage Properties</Button></div>
    {propertiesOpen && <section className="fba-properties-panel" aria-label="Manage table properties">
      <div className="fba-properties-heading"><strong>Table Properties</strong><Button type="link" onClick={() => onPreferences(defaultColumns)}>Reset Columns</Button></div>
      <div className="fba-properties-grid">{known.map((p, index) => <div className="fba-property" key={p.key}>
        <Checkbox checked={p.visible} disabled={p.visible && columns.length === 1} onChange={e => onPreferences(known.map(x => x.key === p.key ? { ...x, visible: e.target.checked } : x))}>{String(defs[p.key].title)}</Checkbox>
        <Space size={0}><Button size="small" type="text" aria-label={`Move ${String(defs[p.key].title)} earlier`} disabled={index === 0} icon={<ArrowUpOutlined />} onClick={() => moveColumn(index, -1)} /><Button size="small" type="text" aria-label={`Move ${String(defs[p.key].title)} later`} disabled={index === known.length - 1} icon={<ArrowDownOutlined />} onClick={() => moveColumn(index, 1)} /></Space>
      </div>)}</div>
    </section>}
    <Table sticky rowKey="id" loading={loading} dataSource={rows} columns={columns}
      rowSelection={{ selectedRowKeys: selected, onChange: keys => onSelected(keys.map(Number)) }}
      scroll={{ x: columns.reduce((sum, column) => sum + Number(column.width), 60) }}
      pagination={{ current: page, pageSize: per, total, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], showTotal: t => `Total ${t} shipments`, itemRender: (_, type, original) => type === 'prev' ? 'Previous' : type === 'next' ? 'Next' : original }}
      onChange={(p, _f, sorter, extra) => {
        if (extra.action === 'paginate') onPage(p)
        if (extra.action === 'sort') {
          const sort = Array.isArray(sorter) ? sorter[0] : sorter
          onSort(sort?.field && sort.order ? String(sort.field) : 'priority_rank', sort.order === 'ascend' ? 'asc' : 'desc')
        }
      }} />
  </div>
}
