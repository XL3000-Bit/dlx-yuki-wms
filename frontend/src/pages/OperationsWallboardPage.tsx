import { ArrowLeftOutlined, FullscreenOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getOperationsDashboard, OperationsDashboard } from '../api/operationsDashboard'
import '../wallboard-neon-fonts.css'
import '../wallboard.css'

const title = (value: string) => value.replaceAll('_', ' ').toLowerCase().replace(/^./, c => c.toUpperCase())

function Panel({ title: heading, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return <section className={`wb-panel ${className}`}><h2><i />{heading}</h2><div className="wb-panel-body">{children}</div></section>
}

function Metric({ value, label }: { value: number | string; label: string }) {
  return <div className="wb-metric"><strong>{value}</strong><span>{label}</span></div>
}

function NetworkMap({ warehouses }: { warehouses: OperationsDashboard['warehouses'] }) {
  const mapUrl = 'https://www.google.com/maps?q=4450%20Edison%20Ave%2C%20Chino%2C%20CA&z=11&output=embed'
  return <div className="wb-map">
    <iframe title="Warehouse map — 4450 Edison Ave" src={mapUrl} loading="eager" referrerPolicy="no-referrer-when-downgrade" allowFullScreen />
    <div className="wb-map-shade" />
    <div className="wb-map-location"><small>PRIMARY OPERATIONS HUB</small><strong>4450 Edison Ave · Chino, CA</strong></div>
    <div className="wb-map-warehouses">{warehouses.slice(0, 5).map(warehouse => <span key={warehouse.warehouse_id}><i className={warehouse.open_exceptions ? 'risk' : 'online'} />{warehouse.warehouse_code}<b>{warehouse.open_work_orders + warehouse.open_exceptions}</b></span>)}</div>
    <div className="wb-map-caption"><span><i className="online" /> Online warehouse</span><span><i className="risk" /> Has open exceptions</span></div>
  </div>
}

function FunnelChart({ items }: { items: OperationsDashboard['execution_funnel'] }) {
  const max = Math.max(...items.map(item => item.count), 1)
  const points = items.map((item, index) => `${items.length === 1 ? 50 : index * (100 / (items.length - 1))},${44 - item.count / max * 34}`).join(' ')
  return <div className="wb-chart"><svg viewBox="0 0 100 50" preserveAspectRatio="none"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#00e8ff" stopOpacity=".55"/><stop offset="1" stopColor="#0076d7" stopOpacity=".03"/></linearGradient></defs><path d={`M0 46 L${points} L100 46 Z`} fill="url(#area)"/><polyline points={points} fill="none" stroke="#20edff" strokeWidth=".8" vectorEffect="non-scaling-stroke"/>{items.map((item, index) => <circle key={item.stage} cx={items.length === 1 ? 50 : index * (100 / (items.length - 1))} cy={44 - item.count / max * 34} r="1" fill="#b9fbff" />)}</svg><div className="wb-chart-labels">{items.map(item => <span key={item.stage}>{title(item.stage)}<b>{item.count}</b></span>)}</div></div>
}

export function OperationsWallboardPage() {
  const navigate = useNavigate()
  const [now, setNow] = useState(dayjs())
  const today = dayjs().format('YYYY-MM-DD')
  const query = useQuery({ queryKey: ['operations-wallboard', today], queryFn: () => getOperationsDashboard({ date_from: today, date_to: today }), refetchInterval: 60000 })
  useEffect(() => { const timer = window.setInterval(() => setNow(dayjs()), 1000); return () => window.clearInterval(timer) }, [])
  const data = query.data
  const health = useMemo(() => { if (!data) return { normal: 100, warning: 0, critical: 0 }; const critical = Math.min(100, Math.round(data.summary.critical_open_exceptions / Math.max(data.summary.open_exceptions, 1) * 100)); const warning = Math.min(100 - critical, Math.round(data.work_orders.overdue_snapshot / Math.max(data.summary.open_work_orders, 1) * 100)); return { normal: 100 - warning - critical, warning, critical } }, [data])
  const fullscreen = () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()
  if (!data) return <div className="wallboard wb-state"><div>{query.isError ? 'Unable to load wallboard data.' : 'Loading operations wallboard…'}</div>{query.isError && <button onClick={() => query.refetch()}>Retry</button>}</div>
  return <main className="wallboard">
    <header className="wb-header"><div className="wb-header-actions"><button onClick={() => navigate('/dashboard')}><ArrowLeftOutlined /> Dashboard</button><button onClick={fullscreen}><FullscreenOutlined /> Fullscreen</button></div><div className="wb-brand" aria-label="DLX YUKI WMS"><span data-text="DLX YUKI">DLX <i className="neon-weak">Y</i>UKI</span><span data-text="WMS">WM<i className="neon-weak">S</i></span></div><div className="wb-clock"><b>{now.format('YYYY-MM-DD')}</b><span>{now.format('HH:mm:ss')}</span><button title="Refresh" onClick={() => query.refetch()}><ReloadOutlined spin={query.isFetching} /></button></div></header>
    <div className="wb-layout">
      <aside className="wb-left">
        <Panel title="Operational overview"><div className="wb-metrics"><Metric value={data.summary.active_loads} label="Active loads"/><Metric value={data.summary.open_work_orders} label="Open work orders"/><Metric value={data.summary.open_exceptions} label="Open exceptions"/></div></Panel>
        <Panel title="Execution health"><div className="wb-health"><div className="wb-donut" style={{ background: `conic-gradient(#62e4c1 0 ${health.normal}%, #e7bf49 ${health.normal}% ${health.normal + health.warning}%, #ff5d6c ${health.normal + health.warning}% 100%)` }}><span><b>{health.normal}%</b>Healthy</span></div><div className="wb-legend"><span><i className="green"/>Healthy {health.normal}%</span><span><i className="yellow"/>Overdue {health.warning}%</span><span><i className="red"/>Critical {health.critical}%</span></div></div></Panel>
        <Panel title="Priority alerts" className="wb-alerts"><div>{data.attention.slice(0, 5).map(item => <article key={`${item.kind}-${item.entity_id}`}><i className={item.kind === 'EXCEPTION' ? 'critical' : ''}/><span><b>{item.reference}</b><small>{item.label || item.message || title(item.reason || item.kind)}</small></span><time>{dayjs(item.since || item.created_at).format('HH:mm')}</time></article>)}{!data.attention.length && <p className="wb-empty">No items require immediate attention</p>}</div></Panel>
      </aside>
      <section className="wb-center"><NetworkMap warehouses={data.warehouses}/><Panel title="Live execution funnel"><FunnelChart items={data.execution_funnel}/></Panel></section>
      <aside className="wb-right">
        <Panel title="Inbound / load activity"><div className="wb-metrics"><Metric value={data.loads.created_period} label="Loads today"/><Metric value={data.summary.outbound_ready} label="Ready"/><Metric value={data.summary.active_loads} label="Active"/></div></Panel>
        <Panel title="Outbound execution"><div className="wb-metrics"><Metric value={data.summary.outbound_active} label="In progress"/><Metric value={data.summary.completed_work_orders_period} label="Completed"/><Metric value={data.work_orders.overdue_snapshot} label="Overdue"/></div></Panel>
        <Panel title="Exceptions"><div className="wb-metrics"><Metric value={data.summary.open_exceptions} label="Open"/><Metric value={data.summary.critical_open_exceptions} label="Critical"/><Metric value={data.exceptions.resolved_period} label="Resolved today"/></div></Panel>
        <Panel title="Warehouse workload" className="wb-bars"><div>{data.warehouses.slice(0, 6).map(item => { const total = item.open_work_orders + item.open_exceptions; return <article key={item.warehouse_id}><span>{item.warehouse_code}</span><div><i style={{ width: `${Math.min(100, total * 8)}%` }}/></div><b>{total}</b></article> })}{!data.warehouses.length && <p className="wb-empty">No active workload</p>}</div></Panel>
      </aside>
    </div>
    <footer>Generated {dayjs(data.meta.generated_at).format('YYYY-MM-DD HH:mm:ss')} · Auto-refresh every 60 seconds · Data restricted to your warehouse access</footer>
  </main>
}
