import {
  Alert, Badge, Button, Card, Col, DatePicker, Empty, List, Progress, Row, Select, Space, Statistic, Table, Tag, Typography,
} from 'antd'
import { ArrowRightOutlined, CheckCircleOutlined, ClockCircleOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import dayjs, { Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getWarehouses } from '../api/masterData'
import { DashboardItem, getOperationsDashboard } from '../api/operationsDashboard'

const { RangePicker } = DatePicker
const iso = (date: Dayjs) => date.format('YYYY-MM-DD')
const pairs = (value: Record<string, number>) => Object.entries(value).map(([key, count]) => ({ key, count }))
const label = (value: string) => value.replaceAll('_', ' ').toLowerCase().replace(/^./, character => character.toUpperCase())

function preset(key: string): [Dayjs, Dayjs] {
  const today = dayjs()
  if (key === 'yesterday') return [today.subtract(1, 'day'), today.subtract(1, 'day')]
  if (key === '7d') return [today.subtract(6, 'day'), today]
  if (key === 'month') return [today.startOf('month'), today]
  return [today, today]
}

function MetricLine({ name, value, danger = false }: { name: string; value: string | number; danger?: boolean }) {
  return <div className="metric-line"><span>{name}</span><b className={danger ? 'metric-danger' : ''}>{value}</b></div>
}

export function OperationsDashboardPage() {
  const navigate = useNavigate()
  const [warehouse, setWarehouse] = useState<number>()
  const [range, setRange] = useState<[Dayjs, Dayjs]>(preset('today'))
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses })
  const params = useMemo(() => ({ date_from: iso(range[0]), date_to: iso(range[1]), warehouse_id: warehouse }), [range, warehouse])
  const query = useQuery({ queryKey: ['operations-dashboard', params], queryFn: () => getOperationsDashboard(params) })
  const data = query.data
  const executionTotal = data?.execution_funnel.reduce((total, item) => total + item.count, 0) ?? 0

  const go = (path: string, filters: Record<string, string | number | undefined>) => {
    const search = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)]))
    navigate(`${path}?${search.toString()}`)
  }
  const openItem = (item: DashboardItem) => navigate(item.kind === 'EXCEPTION' ? `/trouble-shoot?selected=${item.entity_id}` : `/work-orders?selected=${item.entity_id}`)

  const kpis = data ? [
    { title: 'Active Loads', value: data.summary.active_loads, note: 'Live snapshot', action: () => go('/loads', { warehouse_id: warehouse }) },
    { title: 'Outbound Ready', value: data.summary.outbound_ready, note: `${data.summary.outbound_active} currently active`, action: () => go('/outbound/dispatch', { warehouse }) },
    { title: 'Open Work Orders', value: data.summary.open_work_orders, note: 'Live workload', action: () => go('/work-orders', { status: 'OPEN', warehouse_id: warehouse }) },
    { title: 'Overdue Work Orders', value: data.work_orders.overdue_snapshot, note: 'Scheduled and overdue', risk: data.work_orders.overdue_snapshot > 0, action: () => go('/work-orders', { status: 'OPEN', warehouse_id: warehouse }) },
    { title: 'Open Exceptions', value: data.summary.open_exceptions, note: `${data.summary.critical_open_exceptions} critical`, risk: data.summary.critical_open_exceptions > 0, action: () => go('/trouble-shoot', { status: 'OPEN', warehouse_id: warehouse }) },
    { title: 'Completed Work Orders', value: data.summary.completed_work_orders_period, note: `${iso(range[0])} – ${iso(range[1])}`, good: true, action: () => go('/work-orders', { status: 'COMPLETED', warehouse_id: warehouse }) },
  ] : []

  return <div className="page operations-dashboard">
    <div className="page-heading dashboard-heading">
      <div>
        <Typography.Text className="dashboard-eyebrow">DLX YUKI WMS · OPERATIONS</Typography.Text>
        <Typography.Title level={3}>Operations Command Center</Typography.Title>
        <Typography.Text type="secondary">Live workload, execution health, and exceptions requiring action</Typography.Text>
      </div>
      <Space>
        {data?.meta.generated_at && <Typography.Text type="secondary" className="dashboard-updated"><ClockCircleOutlined /> Updated {dayjs(data.meta.generated_at).format('MMM D, HH:mm:ss')}</Typography.Text>}
        <Button icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => query.refetch()}>Refresh</Button>
      </Space>
    </div>

    <Card className="dashboard-control-bar" bordered={false}>
      <div className="dashboard-filters">
        <div className="dashboard-filter-field">
          <Typography.Text type="secondary">Warehouse scope</Typography.Text>
          <Select allowClear value={warehouse} placeholder="All accessible warehouses" options={(warehouses.data ?? []).map(item => ({ value: item.id, label: `${item.warehouse_code} — ${item.warehouse_name}` }))} onChange={setWarehouse} />
        </div>
        <div className="dashboard-filter-field dashboard-period-field">
          <Typography.Text type="secondary">Reporting period</Typography.Text>
          <Space wrap><Space.Compact><Button onClick={() => setRange(preset('today'))}>Today</Button><Button onClick={() => setRange(preset('yesterday'))}>Yesterday</Button><Button onClick={() => setRange(preset('7d'))}>7 days</Button><Button onClick={() => setRange(preset('month'))}>This month</Button></Space.Compact><RangePicker value={range} allowClear={false} onChange={value => value && setRange([value[0]!, value[1]!])} /></Space>
        </div>
        <Typography.Text type="secondary" className="dashboard-scope-note">Snapshot cards show current state. Period cards use the selected date range. Results are restricted to your warehouse access.</Typography.Text>
      </div>
    </Card>

    {query.isError ? <Alert type="error" showIcon message="Unable to load operations dashboard" action={<Button onClick={() => query.refetch()}>Retry</Button>} /> : query.isLoading ? <Row gutter={[12, 12]}>{Array.from({ length: 6 }, (_, index) => <Col xs={24} sm={12} xl={4} key={index}><Card loading /></Col>)}</Row> : !data ? <Empty /> : <>
      <section className="dashboard-section">
        <div className="dashboard-section-heading"><div><Typography.Title level={5}>Operational pulse</Typography.Title><Typography.Text type="secondary">Current state and selected-period throughput</Typography.Text></div></div>
        <Row gutter={[12, 12]}>{kpis.map(item => <Col xs={24} sm={12} lg={8} xxl={4} key={item.title}><Card className={`dashboard-kpi ${item.risk ? 'dashboard-kpi-risk' : ''} ${item.good ? 'dashboard-kpi-good' : ''}`} hoverable onClick={item.action}><Statistic title={item.title} value={item.value} prefix={item.risk ? <WarningOutlined /> : item.good ? <CheckCircleOutlined /> : undefined} /><div className="dashboard-kpi-foot"><Typography.Text type="secondary">{item.note}</Typography.Text><ArrowRightOutlined /></div></Card></Col>)}</Row>
      </section>

      <section className="dashboard-section">
        <div className="dashboard-section-heading"><div><Typography.Title level={5}>Attention first</Typography.Title><Typography.Text type="secondary">Critical exceptions, urgent work orders, and aging work requiring intervention</Typography.Text></div><Badge count={data.attention.length} showZero /></div>
        <Row gutter={[12, 12]}>
          <Col xs={24} xl={16}><Card className="dashboard-attention-card" title="Priority queue" extra={<Typography.Text type="secondary">Top {Math.min(data.attention.length, 10)}</Typography.Text>}><List locale={{ emptyText: 'Nothing needs immediate attention' }} dataSource={data.attention.slice(0, 10)} renderItem={item => <List.Item className="dashboard-link" onClick={() => openItem(item)} actions={[<ArrowRightOutlined key="open" />]}><List.Item.Meta avatar={<span className={`attention-marker ${item.kind === 'EXCEPTION' ? 'exception' : 'work-order'}`} />} title={<Space wrap><Typography.Text strong>{item.reference}</Typography.Text><Tag color="red">{label(item.reason)}</Tag></Space>} description={item.label} /></List.Item>} /></Card></Col>
          <Col xs={24} xl={8}><Card title="Exception risk"><MetricLine name="Critical open" value={data.summary.critical_open_exceptions} danger={data.summary.critical_open_exceptions > 0} />{pairs(data.exceptions.open_severity_snapshot).filter(item => item.key !== 'CRITICAL').map(item => <MetricLine key={item.key} name={label(item.key)} value={item.count} />)}<div className="dashboard-resolution"><Statistic title="Resolved in selected period" value={data.exceptions.resolved_period} /><Typography.Text type="secondary">Average resolution: {data.exceptions.average_resolution_hours_period == null ? '—' : `${data.exceptions.average_resolution_hours_period}h`}</Typography.Text></div></Card></Col>
        </Row>
      </section>

      <section className="dashboard-section">
        <div className="dashboard-section-heading"><div><Typography.Title level={5}>Execution overview</Typography.Title><Typography.Text type="secondary">Real operational distributions; no synthetic trend data</Typography.Text></div></div>
        <Row gutter={[12, 12]}>
          <Col xs={24} xl={8}><Card title="Load flow · selected period"><Statistic title="Loads created" value={data.loads.created_period} /><div className="tag-cloud">{pairs(data.loads.created_period_by_current_status).map(item => <Tag key={item.key}>{label(item.key)} {item.count}</Tag>)}</div><Typography.Text type="secondary">Average outbounds per created load: {data.loads.average_outbounds_per_period_load ?? '—'}</Typography.Text></Card></Col>
          <Col xs={24} xl={8}><Card title="Work order status · live snapshot">{data.execution_funnel.map(item => <div key={item.stage}><MetricLine name={label(item.stage)} value={item.count} /><Progress percent={executionTotal ? Math.round(item.count / executionTotal * 100) : 0} showInfo={false} size="small" /></div>)}</Card></Col>
          <Col xs={24} xl={8}><Card title="Exception types · live snapshot">{pairs(data.exceptions.open_type_snapshot).length ? pairs(data.exceptions.open_type_snapshot).sort((a, b) => b.count - a.count).slice(0, 6).map(item => <div key={item.key}><MetricLine name={label(item.key)} value={item.count} /><Progress percent={data.summary.open_exceptions ? Math.round(item.count / data.summary.open_exceptions * 100) : 0} showInfo={false} size="small" strokeColor="#e58a24" /></div>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No open exceptions" />}</Card></Col>
        </Row>
      </section>

      <section className="dashboard-section"><Row gutter={[12, 12]}>
        <Col xs={24} xl={8}><Card title="Operational aging · live snapshot"><Typography.Text strong>Open work orders · created at</Typography.Text>{pairs(data.work_orders.aging_snapshot).map(item => <MetricLine key={item.key} name={label(item.key)} value={item.count} danger={item.key.includes('24') && item.count > 0} />)}<Typography.Text strong className="dashboard-subheading">Open exceptions · reported at</Typography.Text>{pairs(data.exceptions.aging_snapshot).map(item => <MetricLine key={item.key} name={label(item.key)} value={item.count} danger={item.key.includes('24') && item.count > 0} />)}</Card></Col>
        <Col xs={24} xl={16}><Card title="Warehouse workload" extra={<Typography.Text type="secondary">All accessible warehouses · no pagination</Typography.Text>}><Table size="small" pagination={false} rowKey="warehouse_id" dataSource={data.warehouses} locale={{ emptyText: 'No warehouse workload' }} columns={[{ title: 'Warehouse', render: (_, item) => <Typography.Text strong>{item.warehouse_code} — {item.warehouse_name}</Typography.Text> }, { title: 'Open work orders', dataIndex: 'open_work_orders', align: 'right' }, { title: 'Open exceptions', dataIndex: 'open_exceptions', align: 'right', render: value => <Typography.Text type={value ? 'danger' : undefined}>{value}</Typography.Text> }]} /></Card></Col>
      </Row></section>

      <section className="dashboard-section"><Card title="Recent operational activity" extra={<Typography.Text type="secondary">Latest 10 events</Typography.Text>}><List locale={{ emptyText: 'No recent activity' }} dataSource={data.recent_activity.slice(0, 10)} renderItem={item => <List.Item className="dashboard-link" onClick={() => openItem(item)} actions={[<ArrowRightOutlined key="open" />]}><List.Item.Meta title={<Space><Typography.Text strong>{item.reference}</Typography.Text><Tag>{label(item.event_type)}</Tag></Space>} description={item.message || dayjs(item.created_at).format('MMM D, HH:mm')} /><Tag>{label(item.kind)}</Tag></List.Item>} /></Card></section>
    </>}
  </div>
}
