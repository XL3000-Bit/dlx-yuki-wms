import type { BusinessType, DispatchPlan, Load, LoadExecution } from '../api/loads'

// Refresh at the first expiry; cap the interval to notice revocation elsewhere.
export function evidenceRefreshDelay(data:any, now = Date.now()):number|false {
  const accepted = (data?.checks ?? []).filter((c:any)=>c.status === 'PASS')
  if (!accepted.length) return false
  const expires = accepted.map((c:any)=>Date.parse(c.review?.expires_at)).filter(Number.isFinite)
  return Math.max(250, Math.min(30000, ...expires.map((t:number)=>t-now+100)))
}

export function sameDispatchDomain(load:Load, business:BusinessType) {
  return load.dispatch_business_type === business && (load.outbounds ?? []).every(o=>o.warehouse_id===load.warehouse_id && o.customer_id != null && o.dispatch_business_type===business)
}
export function dispatchRequest(plan:DispatchPlan, operation_id:string) {
  if (plan.status !== 'FINAL') throw new Error('请先锁定完整计划')
  if (!operation_id?.trim() || !Number.isInteger(plan.id) || plan.id <= 0 || !Number.isInteger(plan.content_revision) || plan.content_revision < 0) throw new Error('派发请求缺少有效计划版本或操作标识')
  return {status:'DISPATCHED',plan_id:plan.id,expected_revision:plan.content_revision,operation_id}
}
export function dispatchFailure(error:any):string[] {
  const detail=error?.response?.data?.detail
  if (detail?.checks) return detail.checks.filter((c:any)=>!['PASS','NOT_APPLICABLE'].includes(c.status)).map((c:any)=>`${c.key}: ${c.reason} (${c.reason_code})${c.missing_information?.length ? '；缺少：'+c.missing_information.join('、') : ''}`)
  if (Array.isArray(detail)) return detail.map((d:any)=>`${d.loc?.join('.') ?? ''}: ${d.msg ?? String(d)}`)
  return [typeof detail==='string' ? detail : error?.message ?? '操作失败，请刷新后核对状态']
}

// Resume only the persisted open batch; completed batches cannot accept new scans.
export function openVerificationRun(execution?:LoadExecution):string|null {
  const run=execution?.current_verification_run
  return run?.status==='STARTED' ? run.id : null
}
