import { Tag, Tooltip, theme } from 'antd'

const colors: Record<string, string> = { CRITICAL: 'red', HIGH: 'orange', MEDIUM: 'gold', NORMAL: 'default' }

export function DispatchPriorityTag({ value }: { value?: string | null }) {
  return <Tooltip title="Dispatch Priority: CRITICAL overdue/today; HIGH 1–2 days; MEDIUM 3–5 days; NORMAL later or unscheduled."><Tag color={colors[value || 'NORMAL']}>{value || 'NORMAL'}</Tag></Tooltip>
}

export function DispatchReadinessTag({ value }: { value?: string | null }) {
  const color = value === 'BLOCKED' ? 'red' : value === 'READY' ? 'green' : value === 'PARTIAL' ? 'orange' : value === 'COMPLETED' ? 'blue' : 'default'
  return <Tooltip title="Dispatch Readiness: READY has inventory and allocation; PARTIAL is partly completed; BLOCKED has an exception; NOT_READY lacks inventory/allocation; COMPLETED is finished."><Tag color={color}>{value || 'NOT_READY'}</Tag></Tooltip>
}

export function OutboundDateCell({ value, days }: { value?: string | null; days?: number | null }) {
  const { token } = theme.useToken()
  if (!value) return <Tooltip title="No active scheduled outbound allocation"><span style={{ color: token.colorTextDisabled }}>--</span></Tooltip>
  const color = days == null || days > 5 ? token.colorText : days <= 0 ? token.colorError : days <= 2 ? token.colorWarning : token.colorWarningText
  const [year, month, day] = value.slice(0, 10).split('-')
  return <Tooltip title={`Earliest Outbound: minimum active outbound schedule. Days Remaining: business calendar days from today. Full date ${month}/${day}/${year}.`}><span style={{ color, fontWeight: days != null && days <= 2 ? 600 : 400 }}>{month}/{day}</span></Tooltip>
}
