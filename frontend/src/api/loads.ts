import { api } from './client'
export type BusinessType = 'FBA' | 'PRIVATE'
export type Load = { id:number; dispatch_business_type?:BusinessType|null; load_no:string; warehouse_id:number; warehouse?:{code:string;name:string}; carrier?:{code:string;name:string}|null; status:string; appointment_reference?:string|null; appointment_time?:string|null; destination_name?:string|null; destination_address?:string|null; outbound_count:number; outbounds?:any[]; work_orders?:any[]; active_exception_count?:number; active_exceptions?:{id:number;exception_no:string;severity:string;status:string;title:string}[]; total_pallet_qty:string|number; total_carton_qty:string|number; total_weight_lbs:string|number; total_cbm:string|number; created_at:string; updated_at:string }
export async function getLoads(params:Record<string,unknown>={}) { return (await api.get<{data:Load[];meta:any}>('/loads',{params})).data }
export async function getLoad(id:number) { return (await api.get<Load>(`/loads/${id}`)).data }
export async function createLoad(payload:Record<string,unknown>) { return (await api.post<Load>('/loads',payload)).data }

export async function attachLoadOutbounds(id:number, outboundIds:number[]) { return (await api.post<Load>(`/loads/${id}/outbounds`, outboundIds)).data }

export type ReadinessStatus = 'PASS' | 'BLOCKED' | 'UNKNOWN' | 'NOT_APPLICABLE'
export type ReadinessCheck = { key: string; status: ReadinessStatus; reason_code: string; reason: string; evidence: string[]; missing_information: string[] }
export type DispatchReadiness = { load_id: number; checked_at: string; plan_id: number | null; plan_version: number | null; content_revision: number | null; ready: boolean; checks: ReadinessCheck[]; consistency: string; notice: string }
export async function getLoadDispatchReadiness(id: number, signal?: AbortSignal): Promise<DispatchReadiness> {
  return (await api.get<DispatchReadiness>(`/loads/${id}/dispatch-readiness`, { signal })).data
}
export type DispatchAllocation = { id:number; inventory_allocation_id:number; outbound_id:number; carton_qty:string|number; pallet_qty:string|number; operation_id:string }
export type DispatchPlan = { id:number; version:number; status:string; content_revision:number; lines:{allocation_id:number; carton_qty:string|number; pallet_qty:string|number}[] }
export async function classifyLoadOrder(id:number, business_type:BusinessType) { return (await api.patch(`/loads/orders/${id}/business`, {business_type})).data }
export async function getLoadAllocations(id:number):Promise<DispatchAllocation[]> { return (await api.get(`/loads/${id}/allocations`)).data }
export async function writeLoadAllocation(id:number, payload:Record<string,unknown>) { return (await api.post(`/loads/${id}/allocations`, payload)).data }
export async function getLoadPlans(id:number):Promise<DispatchPlan[]> { return (await api.get(`/loads/${id}/plans`)).data }
export async function createLoadPlan(id:number):Promise<DispatchPlan> { return (await api.post(`/loads/${id}/plans`)).data }
export async function replaceLoadPlanLines(id:number, plan:DispatchPlan, allocations:DispatchAllocation[]) {
  return writeLoadPlanLines(id,plan,allocations.map(a=>({allocation_id:a.id,carton_qty:a.carton_qty,pallet_qty:a.pallet_qty})))
}
export async function writeLoadPlanLines(id:number, plan:DispatchPlan, lines:DispatchPlan['lines']):Promise<DispatchPlan> {
  return (await api.put<DispatchPlan>(`/loads/${id}/plans/${plan.id}/lines`,{expected_revision:plan.content_revision,lines})).data
}
export async function finalizeLoadPlan(id:number, plan:DispatchPlan):Promise<DispatchPlan> { return (await api.post<DispatchPlan>(`/loads/${id}/plans/${plan.id}/finalize`,{expected_revision:plan.content_revision})).data }
export async function updateLoadStatus(id:number, payload:Record<string,unknown>) { return (await api.post(`/loads/${id}/status`,payload)).data }
export async function writeLoadExecution(id:number, action:'stage'|'verify/start'|'verify/scan'|'verify/complete', payload:Record<string,unknown>) { return (await api.post(`/loads/${id}/${action}`,payload)).data }
export type LoadExecution = { load_id:number; staged_quantity:string|number; verification_complete:boolean; manifest_matches:boolean; current_verification_run:{id:string;status:'STARTED'|'COMPLETE'}|null }
export async function getLoadExecution(id:number):Promise<LoadExecution> { return (await api.get<LoadExecution>(`/loads/${id}/execution-summary`)).data }
export async function getLoadEvidence(id:number):Promise<any> { return (await api.get(`/loads/${id}/evidence`)).data }
export async function reviewLoadEvidence(id:number,payload:Record<string,unknown>) { return (await api.post(`/loads/${id}/evidence/reviews`,payload)).data }
export async function generateLoadBol(id:number,outbound_id:number) { return (await api.post(`/loads/${id}/evidence/documents/bol`,{outbound_id})).data }
export async function resolveLoadException(id:number,exceptionId:number,resolution:string) { return (await api.post(`/loads/${id}/evidence/exceptions/${exceptionId}/resolve`,{resolution})).data }
