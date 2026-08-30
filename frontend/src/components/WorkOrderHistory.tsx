import { Alert, Empty, List, Skeleton, Space, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { getWorkOrderEvents, WorkOrderEvent } from '../api/workOrders'

function assignment(value?: string | null) {
  if (!value) return '—'
  try {
    const parsed = JSON.parse(value)
    return [parsed.user_id ? `User #${parsed.user_id}` : '', parsed.team ? `Team ${parsed.team}` : ''].filter(Boolean).join(' / ') || '—'
  } catch { return value }
}

function details(event: WorkOrderEvent) {
  if (event.message) return event.message
  if (event.old_value != null || event.new_value != null) {
    const format = event.field_name === 'assignment' ? assignment : (value?: string | null) => value || '—'
    return `${event.field_name?.replaceAll('_', ' ') ?? 'value'}: ${format(event.old_value)} → ${format(event.new_value)}`
  }
  return '—'
}

export function WorkOrderHistory({ workOrderId }: { workOrderId: number | null }) {
  const query = useQuery({queryKey:['work-order-events',workOrderId],queryFn:()=>getWorkOrderEvents(workOrderId!),enabled:!!workOrderId})
  if (query.isLoading) return <Skeleton active paragraph={{rows:3}} />
  if (query.isError) return <Alert type="error" showIcon message="Unable to load work order history" />
  if (!query.data?.data.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No history records" />
  return <List size="small" dataSource={query.data.data} renderItem={event=><List.Item>
    <Space direction="vertical" size={2} style={{width:'100%'}}>
      <Space wrap><Typography.Text type="secondary">{new Date(event.created_at).toLocaleString()}</Typography.Text><Typography.Text>{event.actor?.display_name || event.actor_name || 'System'}</Typography.Text><Tag>{event.event_type.replaceAll('_',' ')}</Tag></Space>
      <Typography.Text>{details(event)}</Typography.Text>
    </Space>
  </List.Item>} />
}
