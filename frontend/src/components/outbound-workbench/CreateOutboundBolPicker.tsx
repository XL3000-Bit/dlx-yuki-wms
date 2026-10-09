import { Alert, Button, Checkbox, Input, Popover, Select, Space, Table, message } from 'antd'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { exportCargoBols, getCargoBols, type CargoBol } from '../../api/cargoBols'

const fields = [
  ['BOL#', 'bol_no'], ['Type', 'source_type'], ['Group Status', 'status_name'],
  ['Pickup Location', 'warehouse_name'], ['Del Code', 'del_code'], ['Redirect Code', 'redirect_code'],
  ['Transfer Code', 'transfer_code'], ['Weight LB', 'available_weight_lbs'], ['CBM', 'available_cbm'],
  ['Est. OB PLT', 'estimated_ob_pallets'], ['Remaining PLT', 'available_pallet_qty'],
  ['DW', 'delivery_window'], ['ETA', 'eta'], ['APT', 'appointment_time'],
  ['Act. IB Date', 'actual_inbound_date'], ['LFD', 'lfd'], ['Release Status', 'release_status'],
  ['PO#', 'po_number'], ['CNTR#', 'container_number'], ['Remaining CTN', 'available_carton_qty'],
] as const
const numeric = new Set(['available_weight_lbs', 'available_cbm', 'available_pallet_qty', 'available_carton_qty'])
const compactKeys = ['bol_no', 'source_type', 'status_name', 'warehouse_name', 'del_code', 'available_pallet_qty', 'available_weight_lbs', 'available_cbm']
const remainingKeys = ['bol_no', 'source_type', 'status_name', 'warehouse_name', 'del_code', 'redirect_code', 'actual_inbound_date', 'estimated_inbound_date', 'available_pallet_qty', 'container_number']
const remainingFields = [...fields, ['Est. IB Date', 'estimated_inbound_date'] as const]
const format = (value: unknown) => value == null || value === '' ? '—' : String(value)

export default function CreateOutboundBolPicker({ related, compatible, add, remove, onDrag, disabled }: {
  related: CargoBol[]; compatible: (row: CargoBol) => boolean; add: (row: CargoBol) => void
  remove: (row: CargoBol) => void; onDrag: (row: CargoBol) => void; disabled: boolean
}) {
  const [search, setSearch] = useState('')
  const [source, setSource] = useState<string>()
  const [destination, setDestination] = useState('')
  const [filtersVisible, setFiltersVisible] = useState(false)
  const [awaiting, setAwaiting] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [remainingPage, setRemainingPage] = useState(1)
  const [remainingSize, setRemainingSize] = useState(50)
  const [visible, setVisible] = useState<string[]>(fields.map(([, key]) => key))
  const [exporting, setExporting] = useState(false)
  const scope = { warehouse_id: related[0]?.warehouse_id, customer_id: related[0]?.customer_id }
  useEffect(() => { setPage(1); setRemainingPage(1) }, [scope.warehouse_id, scope.customer_id])
  const filters = { ...scope, q: search || undefined, source_type: source, del_code: destination || undefined }
  const candidates = useQuery({ queryKey: ['cargo-bols', 'create', filters, awaiting, page, pageSize], queryFn: () => getCargoBols({ ...filters, remaining_only: awaiting, page, page_size: pageSize }) })
  const remaining = useQuery({ queryKey: ['cargo-bols', 'remaining', filters, remainingPage, remainingSize], queryFn: () => getCargoBols({ ...filters, remaining_only: true, page: remainingPage, page_size: remainingSize }) })
  const resetPages = () => { setPage(1); setRemainingPage(1) }
  const exportRows = async (remainingOnly: boolean) => {
    setExporting(true)
    try { await exportCargoBols({ ...filters, remaining_only: remainingOnly }) }
    catch (error) { message.error(error instanceof Error ? error.message : '导出失败') }
    finally { setExporting(false) }
  }
  const columnsFor = (list: readonly (readonly [string, string])[]) => list.map(([title, dataIndex]) => ({
    title, dataIndex, key: dataIndex, width: dataIndex === 'status_name' ? 170 : 140,
    render: (value: unknown) => numeric.has(dataIndex) && value != null ? Number(value).toFixed(2) : format(value),
  }))
  const mainFields = fields.filter(([, key]) => visible.includes(key))
  const secondaryFields = remainingKeys.map(key => remainingFields.find(([, field]) => field === key)!)
  const selectedKeys = related.map(row => row.id)
  const selection = {
    selectedRowKeys: selectedKeys, preserveSelectedRowKeys: true, hideSelectAll: true,
    getCheckboxProps: (row: CargoBol) => ({ disabled: disabled || (!selectedKeys.includes(row.id) && !compatible(row)) }),
    onSelect: (row: CargoBol, selected: boolean) => { selected ? add(row) : remove(row); resetPages() },
  }
  const summary = (list: readonly (readonly [string, string])[], totals?: Record<string, number | string>) => <Table.Summary>
    {['Selected', 'Total'].map(label => <Table.Summary.Row key={label}>
      <Table.Summary.Cell index={0} />
      {list.map(([, key], index) => <Table.Summary.Cell key={key} index={index + 1}>
        {index === 0 ? label : numeric.has(key) ? (label === 'Selected'
          ? related.reduce((sum, row) => sum + Number(row[key as keyof CargoBol] || 0), 0).toFixed(2)
          : totals?.[key] == null ? '—' : Number(totals[key]).toFixed(2)) : ''}
      </Table.Summary.Cell>)}
    </Table.Summary.Row>)}
  </Table.Summary>
  return <section className="create-ob-picker" aria-label="OB BOL List">
    <div className="create-ob-picker-heading"><h3>OB BOL List</h3>
      <Popover trigger="click" title="Manage Properties" content={<div className="create-ob-properties"><Checkbox.Group value={visible} onChange={values => setVisible(values as string[])} options={fields.map(([label, value]) => ({ label, value, disabled: value === 'bol_no' }))} /></div>}><Button>Manage Properties</Button></Popover>
    </div>
    <Space wrap className="create-ob-toolbar">
      <Select aria-label="Views" value={visible.length === fields.length ? 'all' : visible.length === compactKeys.length && compactKeys.every(key => visible.includes(key)) ? 'compact' : 'custom'} style={{ width: 135 }} options={[{ value: 'all', label: '全部列' }, { value: 'compact', label: '配货常用列' }, { value: 'custom', label: '自定义视图', disabled: true }]} onChange={value => setVisible(value === 'all' ? fields.map(([, key]) => key) : compactKeys)} />
      <Button onClick={() => setFiltersVisible(!filtersVisible)}>{filtersVisible ? 'Hide Filters' : 'Show Filters'}</Button>
      <Button type={awaiting ? 'primary' : 'default'} onClick={() => { setAwaiting(!awaiting); setPage(1) }}>Awaiting Dispatch</Button>
      <Button loading={candidates.isFetching} onClick={() => candidates.refetch()}>Refresh</Button>
      <Button loading={exporting} onClick={() => exportRows(awaiting)}>Export</Button>
    </Space>
    <p className="create-ob-picker-hint">Active Filters: {awaiting ? '可配库存' : '全部 BOL'}{search && ` · ${search}`}{source && ` · ${source}`}{destination && ` · ${destination}`} · 已选 {related.length} 条{related.length > 0 && ' · 已限定同仓库、客户'}</p>
    <Input.Search placeholder="搜索 BOL# / PO# / Source# / 柜号" allowClear onSearch={value => { setSearch(value); resetPages() }} />
    {filtersVisible && <Space wrap className="create-ob-toolbar">
      <Select aria-label="BOL Type" placeholder="Type" allowClear value={source} style={{ width: 160 }} options={['INBOUND', 'FBA', 'HISTORY_OUTBOUND'].map(value => ({ value, label: value }))} onChange={value => { setSource(value); resetPages() }} />
      <Input.Search placeholder="Del Code" allowClear onSearch={value => { setDestination(value); resetPages() }} />
    </Space>}
    {candidates.isError && <Alert type="error" message="BOL 加载失败，请重试" />}
    <Table<CargoBol> bordered size="small" rowKey="id" columns={columnsFor(mainFields)} rowSelection={selection}
      loading={candidates.isFetching} dataSource={candidates.data?.data || []} scroll={{ x: mainFields.length * 140 + 60, y: 480 }}
      rowClassName={row => row.can_allocate ? 'create-ob-stock-row' : ''}
      onRow={row => ({ draggable: compatible(row) && !disabled, onDragStart: event => { onDrag(row); event.dataTransfer.setData('application/yuki-cargo-bol-id', String(row.id)) } })}
      summary={() => summary(mainFields, candidates.data?.meta.totals)}
      pagination={{ current: page, pageSize, total: candidates.data?.meta.total || 0, showSizeChanger: true, pageSizeOptions: [20, 50, 100], showTotal: total => `${total} total`, onChange: (next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size) } }} />
    <div className="create-ob-remaining-heading"><h3>Remaining BOL List</h3><Space><Button loading={remaining.isFetching} onClick={() => remaining.refetch()}>Refresh</Button><Button loading={exporting} onClick={() => exportRows(true)}>Export</Button></Space></div>
    {remaining.isError && <Alert type="error" message="余量列表加载失败，请重试" />}
    <Table<CargoBol> bordered size="small" rowKey="id" columns={columnsFor(secondaryFields)} rowSelection={selection}
      dataSource={remaining.data?.data || []} loading={remaining.isFetching} scroll={{ x: 1500, y: 360 }}
      rowClassName={row => row.can_allocate ? 'create-ob-stock-row' : ''}
      onRow={row => ({ draggable: compatible(row) && !disabled, onDragStart: event => { onDrag(row); event.dataTransfer.setData('application/yuki-cargo-bol-id', String(row.id)) } })}
      summary={() => summary(secondaryFields, remaining.data?.meta.totals)}
      pagination={{ current: remainingPage, pageSize: remainingSize, total: remaining.data?.meta.total || 0, showSizeChanger: true, pageSizeOptions: [20, 50, 100], showTotal: total => `${total} total`, onChange: (next, size) => { setRemainingPage(size === remainingSize ? next : 1); setRemainingSize(size) } }} />
  </section>
}
