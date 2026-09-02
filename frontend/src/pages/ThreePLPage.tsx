import { ApartmentOutlined, ArrowRightOutlined, CalendarOutlined, ClockCircleOutlined, InboxOutlined, ReloadOutlined, SendOutlined, TeamOutlined, WarningOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, Card, Col, DatePicker, Empty, List, Row, Select, Space, Statistic, Table, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import dayjs, { Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCustomers, getWarehouses } from '../api/masterData'
import { getThreePLOverview, ThreePLClient } from '../api/threepl'

const { RangePicker } = DatePicker
const iso = (value: Dayjs) => value.format('YYYY-MM-DD')
const quantity = (value: number, digits = 2) => value.toLocaleString(undefined, { maximumFractionDigits: digits })

export function ThreePLPage() {
  const navigate = useNavigate()
  const [customerId, setCustomerId] = useState<number>()
  const [warehouseId, setWarehouseId] = useState<number>()
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().startOf('month'), dayjs()])
  const customers = useQuery({ queryKey: ['customers'], queryFn: getCustomers })
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses })
  const params = useMemo(() => ({ date_from: iso(range[0]), date_to: iso(range[1]), customer_id: customerId, warehouse_id: warehouseId }), [range, customerId, warehouseId])
  const query = useQuery({ queryKey: ['3pl-overview', params], queryFn: () => getThreePLOverview(params) })
  const data = query.data
  const go = (path: string, customer?: number) => {
    const search = new URLSearchParams()
    if (customer) search.set('customer_id', String(customer))
    if (warehouseId) search.set('warehouse_id', String(warehouseId))
    navigate(`${path}${search.size ? `?${search}` : ''}`)
  }

  const columns = [
    { title: 'Client', key: 'client', fixed: 'left' as const, width: 230, render: (_: unknown, item: ThreePLClient) => <div><Typography.Text strong>{item.customer_code}</Typography.Text><Typography.Text type="secondary" className="threepl-client-name">{item.customer_name}</Typography.Text></div> },
    { title: 'On hand', key: 'inventory', align: 'right' as const, render: (_: unknown, item: ThreePLClient) => <div><Typography.Text strong>{quantity(item.inventory_pallets)} PLT</Typography.Text><Typography.Text type="secondary" className="threepl-table-note">{quantity(item.inventory_cartons)} CTN · {quantity(item.inventory_cbm)} CBM</Typography.Text></div> },
    { title: 'Open work', key: 'work', align: 'right' as const, render: (_: unknown, item: ThreePLClient) => <Space size={4}><Tag color={item.open_inbounds ? 'blue' : undefined}>{item.open_inbounds} IN</Tag><Tag color={item.open_outbounds ? 'purple' : undefined}>{item.open_outbounds} OUT</Tag></Space> },
    { title: 'Period throughput', key: 'throughput', align: 'right' as const, render: (_: unknown, item: ThreePLClient) => `${item.completed_inbounds} IN / ${item.completed_outbounds} OUT` },
    { title: 'Oldest stock', dataIndex: 'oldest_inventory_days', align: 'right' as const, render: (value: number|null) => value == null ? '—' : <Tag color={value >= 30 ? 'orange' : 'green'}>{value} days</Tag> },
    { title: 'Contact', key: 'contact', width: 200, render: (_: unknown, item: ThreePLClient) => <div>{item.contact_name || '—'}<Typography.Text type={item.email ? 'secondary' : 'danger'} className="threepl-table-note">{item.email || 'Email missing'}</Typography.Text></div> },
    { title: '', key: 'action', width: 48, render: (_: unknown, item: ThreePLClient) => <Button type="text" icon={<ArrowRightOutlined />} onClick={() => go('/inventory', item.customer_id)} /> },
  ]

  return <div className="page threepl-page">
    <div className="page-heading threepl-heading">
      <div><Typography.Text className="threepl-eyebrow">CLIENT OPERATIONS · 3PL</Typography.Text><Typography.Title level={3}>3PL Control Tower</Typography.Title><Typography.Text type="secondary">Client inventory, fulfillment workload, and billing-ready operational usage in one view</Typography.Text></div>
      <Space>{data?.meta.generated_at && <Typography.Text type="secondary"><ClockCircleOutlined /> Updated {dayjs(data.meta.generated_at).format('MMM D, HH:mm')}</Typography.Text>}<Button icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => query.refetch()}>Refresh</Button></Space>
    </div>

    <Card className="threepl-filter-card" bordered={false}>
      <div className="threepl-filters"><label><span>Client account</span><Select allowClear showSearch optionFilterProp="label" value={customerId} placeholder="All accessible clients" onChange={setCustomerId} options={(customers.data ?? []).map(item => ({ value:item.id, label:`${item.customer_code} — ${item.customer_name}` }))} /></label><label><span>Warehouse</span><Select allowClear value={warehouseId} placeholder="All accessible warehouses" onChange={setWarehouseId} options={(warehouses.data ?? []).map(item => ({ value:item.id, label:`${item.warehouse_code} — ${item.warehouse_name}` }))} /></label><label className="threepl-period"><span>Service period</span><RangePicker value={range} allowClear={false} onChange={value => value && setRange([value[0]!, value[1]!])} /></label></div>
    </Card>

    {query.isError ? <Alert type="error" showIcon message="Unable to load the 3PL control tower" action={<Button onClick={() => query.refetch()}>Retry</Button>} /> : query.isLoading ? <Row gutter={[12,12]}>{Array.from({length:6},(_,index)=><Col span={4} key={index}><Card loading /></Col>)}</Row> : !data ? <Empty /> : <>
      <section className="threepl-section"><div className="threepl-section-title"><div><Typography.Title level={5}>Portfolio snapshot</Typography.Title><Typography.Text type="secondary">Current position across the selected client and warehouse scope</Typography.Text></div></div><Row gutter={[12,12]}>
        {[{title:'Active clients',value:data.summary.active_clients,icon:<TeamOutlined />},{title:'Inventory pallets',value:quantity(data.summary.inventory_pallets),icon:<ApartmentOutlined />},{title:'Inventory cartons',value:quantity(data.summary.inventory_cartons),icon:<InboxOutlined />},{title:'Open inbound',value:data.summary.open_inbounds,icon:<InboxOutlined />},{title:'Open outbound',value:data.summary.open_outbounds,icon:<SendOutlined />},{title:'Pallets on hold',value:quantity(data.summary.hold_pallets),icon:<WarningOutlined />,risk:data.summary.hold_pallets>0}].map(item=><Col span={4} key={item.title}><Card className={`threepl-kpi ${item.risk?'is-risk':''}`}><Statistic title={item.title} value={item.value} prefix={item.icon}/></Card></Col>)}
      </Row></section>

      <section className="threepl-section"><div className="threepl-section-title"><div><Typography.Title level={5}>Billing-ready usage</Typography.Title><Typography.Text type="secondary">Operational quantities for the selected service period; rates, minimums, discounts, and tax are not applied</Typography.Text></div><Tag color="gold" icon={<CalendarOutlined />}>{data.meta.date_from} → {data.meta.date_to}</Tag></div><Alert className="threepl-billing-note" type="info" showIcon message="Storage pallet-days are an indicative snapshot" description={data.meta.storage_basis} /><Row gutter={[12,12]}>
        <Col span={6}><Card className="threepl-usage"><Statistic title="Receiving" value={data.usage.receiving_orders} suffix="orders"/><Typography.Text type="secondary">{quantity(data.usage.receiving_pallets)} PLT · {quantity(data.usage.receiving_cartons)} CTN</Typography.Text></Card></Col>
        <Col span={6}><Card className="threepl-usage"><Statistic title="Outbound handling" value={data.usage.outbound_orders} suffix="orders"/><Typography.Text type="secondary">{quantity(data.usage.outbound_pallets)} PLT · {quantity(data.usage.outbound_cartons)} CTN</Typography.Text></Card></Col>
        <Col span={6}><Card className="threepl-usage"><Statistic title="Storage exposure" value={quantity(data.usage.storage_pallet_days)} suffix="pallet-days"/><Typography.Text type="secondary">Snapshot basis, ready for rate application</Typography.Text></Card></Col>
        <Col span={6}><Card className="threepl-usage threepl-usage-cta"><Typography.Title level={5}>Service billing</Typography.Title><Typography.Text type="secondary">Usage is ready. Contract rate cards and invoice approval can be added next.</Typography.Text></Card></Col>
      </Row></section>

      <section className="threepl-section"><Row gutter={[12,12]}><Col span={17}><Card title="Client portfolio" extra={<Typography.Text type="secondary">{data.clients.length} accounts</Typography.Text>}><Table className="threepl-table" size="small" rowKey="customer_id" columns={columns} dataSource={data.clients} pagination={{pageSize:8,showSizeChanger:false}} scroll={{x:1050}} /></Card></Col><Col span={7}><Card title="Attention queue" extra={<Badge count={data.attention.length} showZero />}><List className="threepl-attention" dataSource={data.attention.slice(0,8)} locale={{emptyText:'No client issues need attention'}} renderItem={item=><List.Item onClick={()=>go(item.target,item.customer_id)} actions={[<ArrowRightOutlined key="go"/>]}><List.Item.Meta avatar={<span className={`threepl-severity ${item.severity.toLowerCase()}`}/>} title={<Space size={6}><Typography.Text strong>{item.customer_code}</Typography.Text><Tag>{item.title}</Tag></Space>} description={item.detail}/></List.Item>} /></Card></Col></Row></section>
    </>}
  </div>
}
