import {
  ApartmentOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CloseOutlined,
  DownloadOutlined,
  FileAddOutlined,
  InboxOutlined,
  ReloadOutlined,
  SearchOutlined,
  SendOutlined,
  TeamOutlined,
  UserOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Badge,
  Button,
  DatePicker,
  Descriptions,
  Empty,
  Input,
  List,
  message,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getCustomers, getWarehouses } from '../api/masterData'
import { downloadFile, ensureOutboundDocuments } from '../api/pickingBol'
import { getThreePLDispatchQueue, getThreePLOverview, ThreePLClient, ThreePLDispatchTask, ThreePLOverview } from '../api/threepl'

const { RangePicker } = DatePicker
const iso = (value: Dayjs) => value.format('YYYY-MM-DD')
const quantity = (value: number, digits = 2) => value.toLocaleString(undefined, { maximumFractionDigits: digits })
const toNumber = (value: string | null, fallback?: number) => value && /^\d+$/.test(value) && Number(value) > 0 ? Number(value) : fallback
const toDate = (value: string | null) => value && /^\d{4}-\d{2}-\d{2}$/.test(value) && dayjs(value).format('YYYY-MM-DD') === value ? dayjs(value) : undefined
type Stage = 'all' | 'inbound' | 'outbound' | 'hold' | 'attention'

const isStage = (value: string | null): value is Stage => ['all', 'inbound', 'outbound', 'hold', 'attention'].includes(value ?? '')

export function ThreePLPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useSearchParams()
  const [selectedIds, setSelectedIds] = useState<React.Key[]>([])
  const customers = useQuery({ queryKey: ['customers'], queryFn: getCustomers })
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses })

  const customerId = toNumber(search.get('customer_id'))
  const warehouseId = toNumber(search.get('warehouse_id'))
  const view = search.get('view') === 'clients' ? 'clients' : 'dispatch'
  const readiness = ['READY', 'AT_RISK', 'BLOCKED'].includes(search.get('readiness') ?? '') ? search.get('readiness')! : undefined
  const blockerCodes = ['ACTIVE_EXCEPTION', 'OUTBOUND_EXCEPTION', 'OUTBOUND_HOLD', 'OVERDUE', 'OWNER_UNASSIGNED', 'CARRIER_MISSING', 'DOCUMENTS_MISSING', 'BOL_MISSING', 'PICKING_MISSING']
  const blocker = blockerCodes.includes(search.get('blocker') ?? '') ? search.get('blocker')! : undefined
  const priority = ['URGENT', 'HIGH', 'NORMAL', 'LOW'].includes(search.get('priority') ?? '') ? search.get('priority')! : undefined
  const requestedStatus = search.get('status')
  const status = requestedStatus !== null && [0, 1, 2, 3, 4, 7].includes(Number(requestedStatus)) ? Number(requestedStatus) : undefined
  const sort = ['queue', 'priority', 'due_at', 'updated_at', 'reference'].includes(search.get('sort') ?? '') ? search.get('sort')! : 'queue'
  const stage: Stage = isStage(search.get('stage')) ? search.get('stage') as Stage : 'all'
  const selectedId = toNumber(search.get('selected'))
  const searchText = search.get('search') ?? ''
  const page = Math.max(1, toNumber(search.get('page'), 1)!)
  const requestedPageSize = toNumber(search.get('page_size'), 20)!
  const pageSize = [10, 20, 50, 100].includes(requestedPageSize) ? requestedPageSize : 20
  const requestedFrom = toDate(search.get('date_from'))
  const requestedTo = toDate(search.get('date_to'))
  const overviewRange: [Dayjs, Dayjs] = [requestedFrom ?? dayjs().startOf('month'), requestedTo ?? dayjs()]
  const dispatchRange: [Dayjs, Dayjs] | null = requestedFrom && requestedTo ? [requestedFrom, requestedTo] : null

  const patchSearch = (patch: Record<string, string | number | undefined>) => {
    const next = new URLSearchParams(search)
    Object.entries(patch).forEach(([key, value]) => value == null || value === '' ? next.delete(key) : next.set(key, String(value)))
    setSearch(next)
  }

  const params = useMemo(() => ({
    date_from: iso(overviewRange[0]),
    date_to: iso(overviewRange[1]),
    customer_id: customerId,
    warehouse_id: warehouseId,
  }), [customerId, warehouseId, search.get('date_from'), search.get('date_to')])
  const query = useQuery({
    queryKey: ['3pl-overview', params],
    queryFn: () => getThreePLOverview(params),
    enabled: view === 'clients',
  })
  const dispatchParams = useMemo(() => ({
    customer_id: customerId, warehouse_id: warehouseId, status, readiness, blocker, priority,
    search: searchText.trim() || undefined,
    date_from: search.get('date_from') || undefined, date_to: search.get('date_to') || undefined,
    page, page_size: pageSize, sort,
  }), [customerId, warehouseId, status, readiness, blocker, priority, searchText, page, pageSize, sort, search.get('date_from'), search.get('date_to')])
  const dispatchQuery = useQuery({
    queryKey: ['3pl-dispatch-queue', dispatchParams],
    queryFn: () => getThreePLDispatchQueue(dispatchParams),
    enabled: view === 'dispatch',
  })
  const issueDocuments = useMutation({
    mutationFn: ensureOutboundDocuments,
    onSuccess: () => {
      message.success('Picking list and BOL are ready')
      queryClient.invalidateQueries({ queryKey: ['3pl-dispatch-queue'] })
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => message.error(error.response?.data?.detail ?? 'Unable to issue documents'),
  })
  const data = query.data
  const attentionIds = useMemo(() => new Set(data?.attention.map(item => item.customer_id) ?? []), [data?.attention])

  const searchedClients = useMemo(() => {
    const needle = searchText.trim().toLowerCase()
    if (!needle) return data?.clients ?? []
    return (data?.clients ?? []).filter(item => [item.customer_code, item.customer_name, item.contact_name, item.email]
      .some(value => value?.toLowerCase().includes(needle)))
  }, [data?.clients, searchText])

  const stageCounts = useMemo(() => ({
    all: searchedClients.length,
    inbound: searchedClients.filter(item => item.open_inbounds > 0).length,
    outbound: searchedClients.filter(item => item.open_outbounds > 0).length,
    hold: searchedClients.filter(item => item.hold_pallets > 0).length,
    attention: searchedClients.filter(item => attentionIds.has(item.customer_id)).length,
  }), [attentionIds, searchedClients])

  const visibleClients = useMemo(() => searchedClients.filter(item => {
    if (stage === 'inbound') return item.open_inbounds > 0
    if (stage === 'outbound') return item.open_outbounds > 0
    if (stage === 'hold') return item.hold_pallets > 0
    if (stage === 'attention') return attentionIds.has(item.customer_id)
    return true
  }), [attentionIds, searchedClients, stage])

  const selectedClient = data?.clients.find(item => item.customer_id === selectedId)
  const selectedRows = (data?.clients ?? []).filter(item => selectedIds.includes(item.customer_id))
  const detailIndex = selectedClient ? visibleClients.findIndex(item => item.customer_id === selectedClient.customer_id) : -1
  const clientAttention = data?.attention.filter(item => item.customer_id === selectedClient?.customer_id) ?? []

  const go = (path: string, customer?: number) => {
    const targetSearch = new URLSearchParams()
    if (customer) targetSearch.set('customer_id', String(customer))
    if (warehouseId) targetSearch.set('warehouse_id', String(warehouseId))
    navigate(`${path}${targetSearch.size ? `?${targetSearch}` : ''}`)
  }

  const openClient = (client: ThreePLClient) => patchSearch({ selected: client.customer_id })
  const columns: TableColumnsType<ThreePLClient> = [
    {
      title: 'Client', key: 'client', fixed: 'left', width: 220,
      render: (_, item) => <div className="threepl-client-cell"><Typography.Text strong>{item.customer_code}</Typography.Text><Typography.Text type="secondary">{item.customer_name}</Typography.Text></div>,
    },
    {
      title: 'Status', key: 'status', width: 92,
      render: (_, item) => <Tag color={item.is_active ? 'green' : 'default'}>{item.is_active ? 'Active' : 'Inactive'}</Tag>,
    },
    {
      title: 'On hand', key: 'inventory', align: 'right', width: 170,
      render: (_, item) => <div className="threepl-number-cell"><Typography.Text strong>{quantity(item.inventory_pallets)} PLT</Typography.Text><Typography.Text type="secondary">{quantity(item.inventory_cartons)} CTN · {quantity(item.inventory_cbm)} CBM</Typography.Text></div>,
    },
    {
      title: 'Open inbound', dataIndex: 'open_inbounds', align: 'right', width: 112,
      render: value => <Tag color={value ? 'blue' : undefined}>{value}</Tag>,
    },
    {
      title: 'Open outbound', dataIndex: 'open_outbounds', align: 'right', width: 118,
      render: value => <Tag color={value ? 'purple' : undefined}>{value}</Tag>,
    },
    {
      title: 'On hold', dataIndex: 'hold_pallets', align: 'right', width: 100,
      render: value => value ? <Tag color="red">{quantity(value)} PLT</Tag> : '—',
    },
    {
      title: 'Period complete', key: 'throughput', align: 'right', width: 140,
      render: (_, item) => `${item.completed_inbounds} IN / ${item.completed_outbounds} OUT`,
    },
    {
      title: 'Oldest stock', dataIndex: 'oldest_inventory_days', align: 'right', width: 112,
      render: value => value == null ? '—' : <Tag color={value >= 30 ? 'orange' : 'green'}>{value} days</Tag>,
    },
    {
      title: 'Last activity', dataIndex: 'last_activity_at', width: 130,
      render: value => value ? dayjs(value).format('MMM D, YYYY') : '—',
    },
    {
      title: '', key: 'action', fixed: 'right', width: 48,
      render: (_, item) => <Button type="text" aria-label={`Open ${item.customer_code}`} icon={<ArrowRightOutlined />} onClick={event => { event.stopPropagation(); openClient(item) }} />,
    },
  ]

  return <div className="threepl-workbench-page">
    <header className="threepl-workbench-heading">
      <div>
        <Typography.Text className="threepl-eyebrow">CLIENT OPERATIONS · 3PL</Typography.Text>
        <Typography.Title level={3}>3PL Operations Workbench</Typography.Title>
        <Typography.Text type="secondary">Prioritize client work, assign ownership, and clear operational blockers from one queue.</Typography.Text>
      </div>
      <Space wrap>
        <Button icon={<ApartmentOutlined />} onClick={() => go('/inventory', selectedClient?.customer_id)}>Inventory</Button>
        <Button icon={<InboxOutlined />} onClick={() => go('/inbound', selectedClient?.customer_id)}>Receiving</Button>
        <Button icon={<SendOutlined />} onClick={() => go('/outbound/dispatch', selectedClient?.customer_id)}>Outbound</Button>
        <Button type="primary" icon={<ReloadOutlined />} loading={view === 'dispatch' ? dispatchQuery.isFetching : query.isFetching} onClick={() => view === 'dispatch' ? dispatchQuery.refetch() : query.refetch()}>Refresh</Button>
      </Space>
    </header>

    <Tabs
      className="threepl-view-tabs"
      activeKey={view}
      onChange={key => patchSearch({ view: key === 'dispatch' ? undefined : key, selected: undefined, page: 1 })}
      items={[
        { key: 'dispatch', label: <span>Dispatch queue <Badge count={dispatchQuery.data?.summary.total ?? 0} showZero color="#0c87a5" /></span> },
        { key: 'clients', label: <span>Client accounts <Badge count={data?.clients.length ?? 0} showZero /></span> },
      ]}
    />

    <section className={`threepl-filter-bar ${view === 'dispatch' ? 'is-dispatch' : ''}`}>
      <label><span>Search</span><Input allowClear prefix={<SearchOutlined />} value={searchText} placeholder={view === 'dispatch' ? 'Order, client, owner, or blocker' : 'Client, contact, or email'} onChange={event => patchSearch({ search: event.target.value, page: 1 })} /></label>
      <label><span>Client account</span><Select allowClear showSearch optionFilterProp="label" value={customerId} placeholder="All accessible clients" onChange={value => patchSearch({ customer_id: value, selected: undefined, page: 1 })} options={(customers.data ?? []).map(item => ({ value: item.id, label: `${item.customer_code} — ${item.customer_name}` }))} /></label>
      <label><span>Warehouse</span><Select allowClear showSearch optionFilterProp="label" value={warehouseId} placeholder="All warehouses" onChange={value => patchSearch({ warehouse_id: value, selected: undefined, page: 1 })} options={(warehouses.data ?? []).map(item => ({ value: item.id, label: `${item.warehouse_code} — ${item.warehouse_name}` }))} /></label>
      {view === 'dispatch'
        ? <>
          <label><span>Readiness</span><Select allowClear value={readiness} placeholder="All states" onChange={value => patchSearch({ readiness: value, page: 1 })} options={[{ value: 'READY', label: 'Ready' }, { value: 'AT_RISK', label: 'At risk' }, { value: 'BLOCKED', label: 'Blocked' }]} /></label>
          <label><span>Status</span><Select allowClear value={status} placeholder="All statuses" onChange={value => patchSearch({ status: value, page: 1 })} options={[['New', 0], ['On hold', 1], ['In progress', 2], ['Confirmed', 3], ['Dispatched', 4], ['Exception', 7]].map(([label, value]) => ({ label, value }))} /></label>
          <label><span>Priority</span><Select allowClear value={priority} placeholder="All priorities" onChange={value => patchSearch({ priority: value, page: 1 })} options={['URGENT', 'HIGH', 'NORMAL', 'LOW'].map(value => ({ value, label: value }))} /></label>
          <label><span>Blocker</span><Select allowClear value={blocker} placeholder="All blockers" onChange={value => patchSearch({ blocker: value, page: 1 })} options={[['ACTIVE_EXCEPTION', 'Active exception'], ['OUTBOUND_EXCEPTION', 'Outbound exception'], ['OUTBOUND_HOLD', 'Outbound on hold'], ['OVERDUE', 'Overdue'], ['OWNER_UNASSIGNED', 'Owner missing'], ['CARRIER_MISSING', 'Carrier missing'], ['DOCUMENTS_MISSING', 'Documents missing'], ['BOL_MISSING', 'BOL missing'], ['PICKING_MISSING', 'Picking list missing']].map(([value, label]) => ({ value, label }))} /></label>
          <label><span>Due date</span><RangePicker value={dispatchRange} allowClear onChange={value => patchSearch({ date_from: value ? iso(value[0]!) : undefined, date_to: value ? iso(value[1]!) : undefined, page: 1 })} /></label>
          <label><span>Sort</span><Select value={sort} onChange={value => patchSearch({ sort: value === 'queue' ? undefined : value, page: 1 })} options={[['queue', 'Queue priority'], ['priority', 'Priority'], ['due_at', 'Due time'], ['updated_at', 'Recently updated'], ['reference', 'Reference']].map(([value, label]) => ({ value, label }))} /></label>
        </>
        : <label><span>Service period</span><RangePicker value={overviewRange} allowClear={false} onChange={value => value && patchSearch({ date_from: iso(value[0]!), date_to: iso(value[1]!), page: 1 })} /></label>}
    </section>

    {view === 'clients' ? <><Tabs
      className="threepl-stage-tabs"
      activeKey={stage}
      onChange={key => patchSearch({ stage: key === 'all' ? undefined : key, page: 1 })}
      items={[
        { key: 'all', label: <span>All clients <Badge count={stageCounts.all} showZero /></span> },
        { key: 'inbound', label: <span>Open inbound <Badge count={stageCounts.inbound} showZero color="#1677ff" /></span> },
        { key: 'outbound', label: <span>Open outbound <Badge count={stageCounts.outbound} showZero color="#722ed1" /></span> },
        { key: 'hold', label: <span>On hold <Badge count={stageCounts.hold} showZero color="#cf1322" /></span> },
        { key: 'attention', label: <span>Attention <Badge count={stageCounts.attention} showZero color="#d46b08" /></span> },
      ]}
    />

    {query.isError ? <Alert className="threepl-state" type="error" showIcon message="Unable to load the 3PL workbench" action={<Button onClick={() => query.refetch()}>Retry</Button>} /> :
      <main className={`threepl-workbench-body ${selectedClient ? 'has-detail' : ''}`}>
        <section className="threepl-workbench-list">
          <Table<ThreePLClient>
            className="threepl-workbench-table"
            loading={query.isLoading}
            size="small"
            rowKey="customer_id"
            columns={columns}
            dataSource={visibleClients}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No clients match this queue" /> }}
            rowSelection={{ selectedRowKeys: selectedIds, onChange: setSelectedIds, preserveSelectedRowKeys: true }}
            rowClassName={item => `${item.customer_id === selectedId ? 'is-selected ' : ''}${attentionIds.has(item.customer_id) ? 'needs-attention' : ''}`}
            onRow={item => ({ onClick: () => openClient(item) })}
            pagination={{ current: page, pageSize, total: visibleClients.length, showSizeChanger: true, pageSizeOptions: [10, 20, 50], showTotal: total => `${total} clients`, onChange: (nextPage, nextSize) => patchSearch({ page: nextPage, page_size: nextSize }) }}
            scroll={{ x: 1240, y: 'calc(100vh - 388px)' }}
          />
        </section>

        {data && selectedClient && <ClientDetail
          client={selectedClient}
          data={data}
          attention={clientAttention}
          canPrevious={detailIndex > 0}
          canNext={detailIndex >= 0 && detailIndex < visibleClients.length - 1}
          onClose={() => patchSearch({ selected: undefined })}
          onPrevious={() => detailIndex > 0 && openClient(visibleClients[detailIndex - 1])}
          onNext={() => detailIndex >= 0 && detailIndex < visibleClients.length - 1 && openClient(visibleClients[detailIndex + 1])}
          onGo={go}
        />}
      </main>}

    {data && <WorkbenchSummary data={data} selected={selectedRows} />}</> : <DispatchQueue
      tasks={dispatchQuery.data?.tasks ?? []}
      summary={dispatchQuery.data?.summary}
      total={dispatchQuery.data?.total ?? 0}
      loading={dispatchQuery.isLoading}
      error={dispatchQuery.isError}
      page={page}
      pageSize={pageSize}
      onRetry={() => dispatchQuery.refetch()}
      onPage={(nextPage, nextSize) => patchSearch({ page: nextPage, page_size: nextSize })}
      onOpen={target => navigate(target)}
      onEnsureDocuments={id => issueDocuments.mutate(id)}
      issuingId={issueDocuments.isPending ? issueDocuments.variables : undefined}
    />}
  </div>
}

function DispatchQueue({ tasks, summary, total, loading, error, page, pageSize, onRetry, onPage, onOpen, onEnsureDocuments, issuingId }: {
  tasks: ThreePLDispatchTask[]
  summary?: { total:number; ready:number; at_risk:number; blocked:number; overdue:number; unassigned:number }
  total: number
  loading: boolean
  error: boolean
  page: number
  pageSize: number
  onRetry: () => void
  onPage: (page: number, pageSize: number) => void
  onOpen: (target: string) => void
  onEnsureDocuments: (id: number) => void
  issuingId?: number
}) {
  const counts = summary ?? { total: 0, ready: 0, at_risk: 0, blocked: 0, overdue: 0, unassigned: 0 }
  const columns: TableColumnsType<ThreePLDispatchTask> = [
    { title: 'Priority', dataIndex: 'priority', width: 92, render: (value, item) => <Tag title={item.priority_reason} color={{ URGENT: 'red', HIGH: 'orange', NORMAL: 'blue', LOW: 'default' }[value as ThreePLDispatchTask['priority']]}>{value}</Tag> },
    { title: 'Task', key: 'task', width: 190, render: (_, item) => <div className="threepl-client-cell"><Typography.Text strong>{item.reference}</Typography.Text><Typography.Text type="secondary">{item.status_name}{item.work_order_type ? ` · ${item.work_order_type}` : ''}</Typography.Text></div> },
    { title: 'Client', key: 'client', width: 200, render: (_, item) => <div className="threepl-client-cell"><Typography.Text strong>{item.customer_code}</Typography.Text><Typography.Text type="secondary">{item.customer_name}</Typography.Text></div> },
    { title: 'Warehouse', dataIndex: 'warehouse_code', width: 110 },
    { title: 'Due', dataIndex: 'due_at', width: 145, render: (value, item) => value ? <div className="threepl-number-cell"><Typography.Text type={item.is_overdue ? 'danger' : undefined} strong={item.is_overdue}>{dayjs(value).format('MMM D, HH:mm')}</Typography.Text><Typography.Text type="secondary">{item.is_overdue ? 'Overdue' : 'Scheduled'}</Typography.Text></div> : 'Not scheduled' },
    { title: 'Owner', dataIndex: 'owner_name', width: 150, render: value => value ? <span><UserOutlined /> {value}</span> : <Tag color="orange">Unassigned</Tag> },
    { title: 'Readiness', dataIndex: 'queue_state', width: 108, render: value => <Tag color={{ READY: 'green', AT_RISK: 'orange', BLOCKED: 'red' }[value as ThreePLDispatchTask['queue_state']]}>{String(value).replace('_', ' ')}</Tag> },
    {
      title: 'Documents', key: 'documents', width: 220,
      render: (_, item) => <div className="threepl-document-cell">
        <Space size={4} wrap>
          {item.picking_download_url && <Button size="small" icon={<DownloadOutlined />} onClick={event => { event.stopPropagation(); void downloadFile(item.picking_download_url!, `${item.picking_no}.xlsx`).catch(() => message.error('Unable to download picking list')) }}>Pick</Button>}
          {item.bol_download_url && <Button size="small" icon={<DownloadOutlined />} onClick={event => { event.stopPropagation(); void downloadFile(item.bol_download_url!, `${item.bol_no}.pdf`).catch(() => message.error('Unable to download BOL')) }}>BOL</Button>}
          {item.document_state !== 'READY' && <Button size="small" type="link" icon={<FileAddOutlined />} loading={issuingId === item.id} onClick={event => { event.stopPropagation(); onEnsureDocuments(item.id) }}>Issue docs</Button>}
        </Space>
        {item.document_state === 'READY' && <Typography.Text type="secondary">{item.picking_no} · {item.bol_no}</Typography.Text>}
      </div>,
    },
    { title: 'Blocker / dependency', key: 'blocker', width: 220, render: (_, item) => item.blocker ? <Typography.Text title={item.blocker_code ? `${item.blocker_label}: ${item.blocker}` : item.blocker} type={item.queue_state === 'BLOCKED' ? 'danger' : undefined}>{item.blocker_label ? `${item.blocker_label}: ${item.blocker}` : item.blocker}</Typography.Text> : <Typography.Text type="secondary">{item.carrier_name ? `Carrier: ${item.carrier_name}` : 'No active blocker'}</Typography.Text> },
    { title: '', key: 'action', fixed: 'right', width: 132, render: (_, item) => <Button size="small" disabled={!item.action_allowed} title={item.action_disabled_reason ?? undefined} type={item.queue_state === 'BLOCKED' ? 'primary' : 'default'} danger={item.queue_state === 'BLOCKED'} onClick={event => { event.stopPropagation(); if (item.action_allowed) onOpen(item.action_target) }}>{item.exception_id ? 'Resolve issue' : item.work_order_id ? 'Open work order' : 'Open outbound'}</Button> },
  ]
  if (error) return <Alert className="threepl-state" type="error" showIcon message="Unable to load the dispatch queue" action={<Button onClick={onRetry}>Retry</Button>} />
  return <main className="threepl-dispatch">
    <section className="threepl-dispatch-summary">
      <Statistic title="Open tasks" value={counts.total} />
      <Statistic title="Ready" value={counts.ready} valueStyle={{ color: '#389e0d' }} />
      <Statistic title="At risk" value={counts.at_risk} valueStyle={{ color: '#d46b08' }} />
      <Statistic title="Blocked" value={counts.blocked} valueStyle={{ color: '#cf1322' }} />
      <Statistic title="Overdue" value={counts.overdue} />
      <Statistic title="Unassigned" value={counts.unassigned} />
    </section>
    <section className="threepl-dispatch-table">
      <Table<ThreePLDispatchTask>
        loading={loading}
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={tasks}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No dispatch work matches these filters" /> }}
        rowClassName={item => `queue-${item.queue_state.toLowerCase().replace('_', '-')}`}
        onRow={item => ({ onClick: () => item.action_allowed && onOpen(item.action_target) })}
        pagination={{ current: page, pageSize, total, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], showTotal: value => `${value} tasks`, onChange: onPage }}
        scroll={{ x: 1570, y: 'calc(100vh - 430px)' }}
      />
    </section>
  </main>
}

function ClientDetail({ client, data, attention, canPrevious, canNext, onClose, onPrevious, onNext, onGo }: {
  client: ThreePLClient
  data: ThreePLOverview
  attention: ThreePLOverview['attention']
  canPrevious: boolean
  canNext: boolean
  onClose: () => void
  onPrevious: () => void
  onNext: () => void
  onGo: (path: string, customer?: number) => void
}) {
  return <aside className="threepl-detail">
    <div className="threepl-detail-head">
      <div><Typography.Text className="threepl-detail-code">{client.customer_code}</Typography.Text><Typography.Title level={4}>{client.customer_name}</Typography.Title></div>
      <Space size={2}><Button type="text" aria-label="Previous client" disabled={!canPrevious} icon={<ArrowLeftOutlined />} onClick={onPrevious} /><Button type="text" aria-label="Next client" disabled={!canNext} icon={<ArrowRightOutlined />} onClick={onNext} /><Button type="text" aria-label="Close details" icon={<CloseOutlined />} onClick={onClose} /></Space>
    </div>
    <div className="threepl-detail-tags"><Tag color={client.is_active ? 'green' : 'default'}>{client.is_active ? 'Active client' : 'Inactive client'}</Tag>{attention.length > 0 && <Tag color="orange" icon={<WarningOutlined />}>{attention.length} attention item{attention.length === 1 ? '' : 's'}</Tag>}</div>
    <Tabs
      className="threepl-detail-tabs"
      items={[
        { key: 'overview', label: 'Overview', children: <>
          <div className="threepl-detail-stats"><Statistic title="Pallets" value={quantity(client.inventory_pallets)} /><Statistic title="Cartons" value={quantity(client.inventory_cartons)} /><Statistic title="CBM" value={quantity(client.inventory_cbm)} /><Statistic title="On hold" value={quantity(client.hold_pallets)} valueStyle={client.hold_pallets ? { color: '#cf1322' } : undefined} /></div>
          <Typography.Title level={5}>Current workload</Typography.Title>
          <div className="threepl-workload"><button onClick={() => onGo('/inbound', client.customer_id)}><InboxOutlined /><strong>{client.open_inbounds}</strong><span>Open inbound</span></button><button onClick={() => onGo('/outbound/dispatch', client.customer_id)}><SendOutlined /><strong>{client.open_outbounds}</strong><span>Open outbound</span></button></div>
          <Typography.Title level={5}>Account</Typography.Title>
          <Descriptions size="small" column={1} colon={false} items={[
            { key: 'contact', label: 'Contact', children: client.contact_name || '—' },
            { key: 'email', label: 'Email', children: client.email || <Typography.Text type="danger">Missing</Typography.Text> },
            { key: 'oldest', label: 'Oldest inventory', children: client.oldest_inventory_days == null ? '—' : `${client.oldest_inventory_days} days` },
            { key: 'activity', label: 'Last activity', children: client.last_activity_at ? dayjs(client.last_activity_at).format('MMM D, YYYY HH:mm') : '—' },
          ]} />
        </> },
        { key: 'period', label: 'Period activity', children: <>
          <Alert type="info" showIcon message={`${data.meta.date_from} to ${data.meta.date_to}`} description="Completed operational activity in the selected service period." />
          <div className="threepl-period-stats"><Statistic title="Completed inbound" value={client.completed_inbounds} suffix="orders" /><Statistic title="Completed outbound" value={client.completed_outbounds} suffix="orders" /></div>
          <Typography.Text type="secondary">Use the portfolio summary below for aggregate receiving, outbound handling, and storage pallet-day quantities.</Typography.Text>
        </> },
        { key: 'attention', label: <span>Attention <Badge count={attention.length} showZero /></span>, children: <List className="threepl-detail-attention" dataSource={attention} locale={{ emptyText: 'No client issues need attention' }} renderItem={item => <List.Item actions={[<Button type="link" key="open" onClick={() => onGo(item.target, client.customer_id)}>Open</Button>]}><List.Item.Meta avatar={<span className={`threepl-severity ${item.severity.toLowerCase()}`} />} title={item.title} description={item.detail} /></List.Item>} /> },
      ]}
    />
    <div className="threepl-detail-actions"><Button block icon={<ApartmentOutlined />} onClick={() => onGo('/inventory', client.customer_id)}>View inventory</Button><Button block icon={<SendOutlined />} onClick={() => onGo('/outbound/dispatch', client.customer_id)}>Open outbound</Button></div>
  </aside>
}

function WorkbenchSummary({ data, selected }: { data: ThreePLOverview; selected: ThreePLClient[] }) {
  const selectedTotals = selected.reduce((totals, item) => ({
    pallets: totals.pallets + item.inventory_pallets,
    inbound: totals.inbound + item.open_inbounds,
    outbound: totals.outbound + item.open_outbounds,
    hold: totals.hold + item.hold_pallets,
  }), { pallets: 0, inbound: 0, outbound: 0, hold: 0 })
  return <footer className="threepl-summary">
    <div className="threepl-summary-group"><strong><TeamOutlined /> Portfolio</strong><Statistic title="Active clients" value={data.summary.active_clients} /><Statistic title="Inventory" value={quantity(data.summary.inventory_pallets)} suffix="PLT" /><Statistic title="Open inbound" value={data.summary.open_inbounds} /><Statistic title="Open outbound" value={data.summary.open_outbounds} /><Statistic title="On hold" value={quantity(data.summary.hold_pallets)} suffix="PLT" /></div>
    <div className="threepl-summary-group is-selected"><strong>{selected.length ? `${selected.length} selected` : 'Period usage'}</strong>{selected.length ? <><Statistic title="Inventory" value={quantity(selectedTotals.pallets)} suffix="PLT" /><Statistic title="Open inbound" value={selectedTotals.inbound} /><Statistic title="Open outbound" value={selectedTotals.outbound} /><Statistic title="On hold" value={quantity(selectedTotals.hold)} suffix="PLT" /></> : <><Statistic title="Receiving" value={data.usage.receiving_orders} suffix="orders" /><Statistic title="Outbound" value={data.usage.outbound_orders} suffix="orders" /><Statistic title="Storage" value={quantity(data.usage.storage_pallet_days)} suffix="pallet-days" /></>}</div>
  </footer>
}
