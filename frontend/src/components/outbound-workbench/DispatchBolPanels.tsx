import { useEffect, useState } from 'react'
import { Button, Checkbox, Descriptions, Input, Modal, Popover, Select, Space, Table, Tag, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assignCargoBols, exportCargoBols, getCargoBol, getCargoBols, type CargoBol, type CargoBolFilters } from '../../api/cargoBols'
import { getCustomers, getWarehouses } from '../../api/masterData'
import { useTableScrollHeight } from '../../hooks/useTableScrollHeight'
import { OutboundVerticalSplitLayout } from './OutboundSplitLayout'

type Target = { id: number; ob_no: string; warehouse_id: number; customer_id?: number; ob_type: string; fba_shipment_id?: number; allowed_actions?: { allocate?: boolean } }
const value = (v: unknown) => v === null || v === undefined || v === '' ? '—' : String(v)
const sourceLabels: Record<string, string> = { INBOUND: '入库货物', FBA: 'FBA 货件', HISTORY_OUTBOUND: '历史出库' }
const fields = [
  ['BOL#', 'bol_no', 175], ['PO#', 'po_number', 170], ['Source#', 'source_no', 165],
  ['Type', 'source_type', 110], ['Status', 'status_name', 175],
  ['Pickup Location', 'warehouse_name', 145], ['Customer', 'customer_name', 150],
  ['Del Code', 'del_code', 110], ['CNTR#', 'container_number', 165],
  ['Available PLT', 'available_pallet_qty', 125], ['Available CTN', 'available_carton_qty', 125],
  ['Available Weight LB', 'available_weight_lbs', 155], ['Available CBM', 'available_cbm', 125],
  ['Lot#', 'lot_no', 155],
] as const
const totalFields = new Set<string>(['available_pallet_qty', 'available_carton_qty', 'available_weight_lbs', 'available_cbm'])
const sum = (rows: readonly CargoBol[], field: string) => rows.reduce((n, r) => n + (Number(r[field as keyof CargoBol]) || 0), 0).toFixed(2)

function CargoPane({ remaining = false, target, onDetail }: { remaining?: boolean; target?: Target; onDetail: (id: number) => void }) {
  const cache = useQueryClient()
  const [filters, setFilters] = useState<CargoBolFilters>({})
  const [page, setPage] = useState(1), [size, setSize] = useState(10)
  const [showFilters, setShowFilters] = useState(false), [selected, setSelected] = useState<React.Key[]>([])
  const [visible, setVisible] = useState<string[]>(fields.map(f => f[1]))
  const [exporting, setExporting] = useState(false)
  const params = { ...filters, remaining_only: remaining }
  const listing = useQuery({ queryKey: ['cargo-bols', remaining ? 'remaining' : 'all', params, page, size], queryFn: () => getCargoBols({ ...params, page, page_size: size }) })
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses, enabled: showFilters })
  const customers = useQuery({ queryKey: ['customers'], queryFn: getCustomers, enabled: showFilters })
  const changeFilter = (next: CargoBolFilters) => { setFilters(next); setPage(1); setSelected([]) }
  useEffect(() => { setSelected([]) }, [target?.id, target?.warehouse_id, target?.customer_id, target?.ob_type, target?.fba_shipment_id, target?.allowed_actions?.allocate])
  const compatible = (row: CargoBol) => !!target?.allowed_actions?.allocate && row.can_allocate
    && row.warehouse_id === target.warehouse_id && row.customer_id === target.customer_id
    && (target.ob_type === 'FBA' ? row.source_type === 'FBA' && row.fba_shipment_id === target.fba_shipment_id : row.source_type === 'INBOUND')
  const rows = listing.data?.data || []
  const selectedRows = rows.filter(row => selected.includes(row.id))
  const assign = useMutation({
    mutationFn: () => assignCargoBols(target!.id, selected.map(Number)),
    onSuccess: result => {
      setSelected([]); message.success(`已将 ${result.bol_count} 条 BOL 的当前余量配入 ${result.ob_no}`)
      for (const key of ['cargo-bols', 'outbound-workbench', 'outbound-workbench-detail', 'inventory', 'picking', 'fba']) cache.invalidateQueries({ queryKey: [key] })
    },
    onError: (error: any) => message.error(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : '配货失败，请刷新后重试'),
  })
  const [tableRef, tableHeight] = useTableScrollHeight(172, 70)
  const columns = fields.filter(f => visible.includes(f[1])).map(([title, dataIndex, width]) => ({
    title, dataIndex, width, ellipsis: true, render: (v: unknown, row: CargoBol) => dataIndex === 'bol_no'
      ? <Button type="link" size="small" onClick={() => onDetail(row.id)}>{value(v)}</Button>
      : dataIndex === 'source_type' ? sourceLabels[String(v)] || value(v)
      : dataIndex === 'status_name' ? <Tag color={row.historical ? 'default' : row.can_allocate ? 'green' : undefined}>{value(v)}</Tag>
      : totalFields.has(dataIndex) ? Number(v || 0).toFixed(2) : value(v),
  }))
  const download = async () => {
    setExporting(true)
    try { await exportCargoBols(params) }
    catch (error: any) { message.error(error.message || '导出失败，请重试') }
    finally { setExporting(false) }
  }
  return <section className="dispatch-bol-panel" aria-label={remaining ? 'Remaining BOL List' : 'OB BOL List'}>
    <div className="panel-title"><strong>{remaining ? 'Remaining BOL List' : 'OB BOL List'}</strong><Space wrap size={4}>
      {remaining && <Button size="small" type="primary" loading={assign.isPending}
        disabled={listing.isFetching || listing.isError || !selected.length || selectedRows.length !== selected.length || !selectedRows.every(compatible)}
        onClick={() => assign.mutate()}>配入选中 OB（全量）</Button>}
      <Popover trigger="click" title="Manage Properties" content={<Checkbox.Group value={visible}
        options={fields.map(f => ({ label: f[0], value: f[1], disabled: f[1] === 'bol_no' }))}
        onChange={v => setVisible(v as string[])} />}><Button size="small">Manage Properties</Button></Popover>
      <Button size="small" onClick={() => setShowFilters(!showFilters)}>{showFilters ? 'Hide Filters' : 'Show Filters'}{Object.values(filters).some(Boolean) ? ' •' : ''}</Button>
      <Button size="small" disabled={assign.isPending} onClick={() => { setSelected([]); listing.refetch() }}>Refresh</Button>
      <Button size="small" loading={exporting} onClick={download}>导出筛选结果</Button>
    </Space></div>
    {remaining && <div className="dispatch-bol-target">{target ? `配货目标：${target.ob_no} · 仅可选择相同仓库、客户及货源类型${target.allowed_actions?.allocate ? '' : '（当前不可配货）'}` : '先在左侧选中一张可配货 OB，再勾选货物。'}</div>}
    {showFilters && <div className="dispatch-bol-filters">
      <Input.Search allowClear aria-label={remaining ? '查找可配 BOL 或 PO' : '查找 BOL 或 PO'} placeholder="BOL# / PO# / Source# / 柜号" value={filters.q || ''}
        onChange={event => changeFilter({ ...filters, q: event.target.value || undefined })} />
      <Select allowClear showSearch optionFilterProp="label" placeholder="仓库" aria-label={remaining ? '可配货仓库' : 'BOL 仓库'} value={filters.warehouse_id}
        options={warehouses.data?.map(w => ({ label: w.warehouse_name, value: w.id }))} onChange={warehouse_id => changeFilter({ ...filters, warehouse_id })} />
      <Select allowClear showSearch optionFilterProp="label" placeholder="客户" aria-label={remaining ? '可配货客户' : 'BOL 客户'} value={filters.customer_id}
        options={customers.data?.map(c => ({ label: c.customer_name, value: c.id }))} onChange={customer_id => changeFilter({ ...filters, customer_id })} />
      <Select allowClear placeholder="货源类型" aria-label={remaining ? '可配货类型' : 'BOL 类型'} value={filters.source_type}
        options={Object.entries(sourceLabels).filter(([key]) => !remaining || key !== 'HISTORY_OUTBOUND').map(([value, label]) => ({ value, label }))}
        onChange={source_type => changeFilter({ ...filters, source_type })} />
      <Input allowClear placeholder="Del Code（精确匹配）" aria-label={remaining ? '可配货目的地' : 'BOL 目的地'} value={filters.del_code || ''}
        onChange={event => changeFilter({ ...filters, del_code: event.target.value || undefined })} />
      <Button onClick={() => changeFilter({})}>清空筛选</Button>
    </div>}
    {listing.isError && <div role="alert">BOL 列表加载失败，请点击 Refresh 重试。</div>}
    <div className="dispatch-bol-table" ref={tableRef}><Table<CargoBol> size="small" rowKey="id" tableLayout="fixed" dataSource={rows} columns={columns} loading={listing.isFetching}
      onRow={row => ({ onDoubleClick: () => onDetail(row.id) })} scroll={{ x: columns.reduce((width, column) => width + column.width, 48), y: tableHeight }}
      rowSelection={{ selectedRowKeys: selected, onChange: setSelected, getCheckboxProps: row => ({ disabled: assign.isPending || (remaining && !compatible(row)) }) }}
      summary={pageRows => <Table.Summary fixed="bottom">
        {[{ label: '已选', rows: pageRows.filter(r => selected.includes(r.id)) }, { label: '本页合计', rows: pageRows }].map(group => <Table.Summary.Row key={group.label}>
          <Table.Summary.Cell index={0} />
          {columns.map((column, i) => <Table.Summary.Cell key={column.dataIndex} index={i + 1}>
            {i === 0 ? <strong>{group.label}</strong> : totalFields.has(column.dataIndex) ? <strong>{sum(group.rows, column.dataIndex)}</strong> : null}
          </Table.Summary.Cell>)}
        </Table.Summary.Row>)}
      </Table.Summary>}
      locale={{ emptyText: remaining ? '暂无符合筛选条件的可配货物。历史记录须先核对并转为实际库存。' : '暂无符合筛选条件的 BOL' }}
      pagination={{ current: page, pageSize: size, total: listing.data?.meta.total || 0, showTotal: total => `${total} BOL`,
        showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], onChange: (p, s) => { setPage(p); setSize(s); setSelected([]) } }} /></div>
  </section>
}

export default function DispatchBolPanels({ onSelect, selectedOutbound }: { onSelect: (id: number) => void; selectedOutbound?: Target }) {
  const [detailId, setDetailId] = useState<number>()
  const detail = useQuery({ queryKey: ['cargo-bols', 'detail', detailId], queryFn: () => getCargoBol(detailId!), enabled: !!detailId })
  return <>
    <OutboundVerticalSplitLayout defaultTopRatio={0.62} storageKey="dlx_wms:dispatch_bol_panels:top_height"
      top={<CargoPane onDetail={setDetailId} />}
      bottom={<CargoPane remaining target={selectedOutbound} onDetail={setDetailId} />} />
    <Modal open={!!detailId} title={detail.data?.bol_no || 'BOL 详情'} onCancel={() => setDetailId(undefined)} footer={null} width={900}>
      {detail.isLoading ? '正在加载…' : detail.isError ? <div role="alert">详情加载失败，请关闭后重试。</div> : detail.data && <>
        <Descriptions size="small" bordered column={2} items={fields.map(([label, key]) => ({ key, label, children: value(detail.data![key]) }))} />
        <p>关联 OB（每行对应一条实际配货记录）</p><Table size="small" rowKey="allocation_id" pagination={false} dataSource={detail.data.outbounds || []} columns={[
          { title: 'OB#', dataIndex: 'ob_no', render: (v, row) => <Button type="link" onClick={() => { onSelect(row.id); setDetailId(undefined) }}>{v}</Button> },
          { title: '已分配 PLT', dataIndex: 'allocated_pallet_qty' }, { title: '已分配 CTN', dataIndex: 'allocated_carton_qty' },
          { title: '已出库 PLT', dataIndex: 'completed_pallet_qty' },
        ]} locale={{ emptyText: '尚未分配至 OB' }} />
      </>}
    </Modal>
  </>
}
