import { Alert, Button, Card, Descriptions, Space, Spin, Tag, Typography } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { getLoadDispatchReadiness } from '../api/loads'
import { createReadinessReader, planValue, readinessPresentation, type ReadinessState } from './loadReadinessState'

export function LoadDispatchReadiness({ loadId, refreshToken = 0 }: { loadId: number; refreshToken?: number }) {
  const qc = useQueryClient()
  const [snapshot, setSnapshot] = useState<{ id: number; state: ReadinessState }>()
  const reader = useRef<ReturnType<typeof createReadinessReader> | null>(null)
  useEffect(() => {
    const next = createReadinessReader(getLoadDispatchReadiness, state => setSnapshot({ id: loadId, state }))
    reader.current = next
    void next.refresh(loadId)
    return () => { next.dispose(); reader.current = null }
  }, [loadId, refreshToken])
  const state: ReadinessState = snapshot?.id === loadId ? snapshot.state : { kind: 'loading' }
  return <Card title="派发只读预检" extra={<Button disabled={state.kind === 'loading'} onClick={() => { void qc.invalidateQueries({queryKey:['load-evidence',loadId]}); void reader.current?.refresh(loadId) }}>刷新预检</Button>}>
    <Space direction="vertical" style={{ width: '100%' }}>
      <Alert type="warning" message="已接入实际派发阻断；只读预检不构成派发授权。" description="结果仅代表检查时刻，不保证后续仍有效。" />
      {state.kind === 'loading' && <Spin tip="正在读取预检" ><div style={{ minHeight: 48 }} /></Spin>}
      {state.kind === 'denied' && <Alert type="error" message="无法访问此对象的预检" description="访问被拒绝或对象不可见；未取得本次检查结果。" />}
      {state.kind === 'unavailable' && <Alert type="error" message="预检技术不可用" description="未取得本次检查结果，请稍后刷新。此错误不代表业务检查 UNKNOWN 或通过。" />}
      {state.kind === 'success' && <>
        <Alert type={state.data.ready ? 'success' : 'warning'} message={state.data.ready ? '后端结论：已具备充分证据' : '后端结论：尚不能确认可派发'} />
        <Descriptions size="small" column={1} items={[
          { key: 'time', label: '检查时间', children: state.data.checked_at },
          { key: 'plan', label: '计划标识', children: planValue(state.data.plan_id) },
          { key: 'version', label: '计划版本', children: planValue(state.data.plan_version) },
          { key: 'revision', label: '内容修订号', children: planValue(state.data.content_revision) },
        ]} />
        {state.data.checks.map(check => <Card size="small" key={check.key} title={check.key}>
          <Tag color={readinessPresentation[check.status].color}>{readinessPresentation[check.status].label}</Tag>
          <Typography.Paragraph>{check.reason_code}：{check.reason}</Typography.Paragraph>
          <div>证据引用：{check.evidence.length ? check.evidence.join('；') : '无'}</div>
          <div>缺失信息：{check.missing_information.length ? check.missing_information.join('；') : '无'}</div>
        </Card>)}
        <Typography.Paragraph type="secondary">{state.data.consistency}<br />{state.data.notice}</Typography.Paragraph>
      </>}
    </Space>
  </Card>
}
