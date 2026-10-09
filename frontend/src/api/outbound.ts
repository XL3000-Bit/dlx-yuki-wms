import { api } from './client'
import type { OutboundAllocation, OutboundParams, OutboundRecord, OutboundResponse } from '../types/outbound'
export type DispatchReadinessCheck = { key: string; code?: string | null; label: string; passed: boolean; reason: string | null; route: string | null }
export type DispatchReadiness = { status: 'READY' | 'NOT_READY'; checks: DispatchReadinessCheck[]; blocking_codes: string[]; blocking_reasons: string[]; error_code?: string | null }
export type OutboundBatchAction = 'confirm' | 'dispatch' | 'complete' | 'cancel' | 'delete'
export type OutboundBatchResult = { id: number; status: 'success' | 'failed'; reason?: string | null }
export type OutboundBatchResponse = { results: OutboundBatchResult[]; successful: number; failed: number }
export type OutboundInventoryBatchAction = 'allocate' | 'release'
export type OutboundInventoryBatchItem = { id: number; data: Record<string, unknown> }
export type OutboundInventoryBatchResponse = OutboundBatchResponse & { action: OutboundInventoryBatchAction }
export const getOutbounds = async (params: OutboundParams) => (await api.get<OutboundResponse>('/outbounds', { params })).data
export const getOutboundWorkbench = async (params: Record<string, unknown>) => (await api.get('/outbounds/workbench', { params })).data
export const getOutboundWorkbenchDetail = async (id: number) => (await api.get(`/outbounds/${id}/workbench-detail`)).data
export const getOutboundDispatchReadiness = async (id: number) => (await api.get<DispatchReadiness>(`/outbounds/${id}/dispatch-readiness`)).data
export const runOutboundWorkbenchBatch = async (action: OutboundBatchAction, ids: number[]) => (await api.post<OutboundBatchResponse>('/outbounds/workbench/batch', { action, ids })).data
export const runOutboundInventoryBatch = async (id: number, action: OutboundInventoryBatchAction, items: OutboundInventoryBatchItem[]) => (await api.post<OutboundInventoryBatchResponse>(`/outbounds/${id}/inventory/batch`, { action, items })).data
export const createOutbound = async (data: Record<string, unknown>) => (await api.post<OutboundRecord>('/outbounds', data)).data
export const updateOutbound = async (id: number, data: Record<string, unknown>) => (await api.put<OutboundRecord>(`/outbounds/${id}`, data)).data
export const updateOutboundSchedule = async (id: number, data: Record<string, unknown>) => (await api.patch<OutboundRecord>(`/outbounds/${id}/schedule`, data)).data
export const getOutboundAllocations = async (id: number) => (await api.get<OutboundAllocation[]>(`/outbounds/${id}/allocations`)).data
export const allocateOutbound = async (id: number, data: Record<string, unknown>) => (await api.post<OutboundAllocation>(`/outbounds/${id}/allocate`, data)).data
export const releaseOutbound = async (id: number, allocationId: number, data: Record<string, unknown>) => (await api.post<OutboundAllocation>(`/outbounds/${id}/allocations/${allocationId}/release`, data)).data
export const confirmOutbound = async (id: number) => (await api.post<OutboundRecord>(`/outbounds/${id}/confirm`)).data
export const dispatchOutbound = async (id: number) => (await api.post<OutboundRecord>(`/outbounds/${id}/dispatch`)).data
export const completeOutbound = async (id: number) => (await api.post<OutboundRecord>(`/outbounds/${id}/complete`)).data
export const cancelOutbound = async (id: number) => (await api.post<OutboundRecord>(`/outbounds/${id}/cancel`)).data
export const exceptionOutbound = async (id: number, reason: string, remark?: string) => (await api.post<OutboundRecord>(`/outbounds/${id}/exception`, { reason, remark })).data
export const resolveOutbound = async (id: number) => (await api.post<OutboundRecord>(`/outbounds/${id}/resolve-exception`)).data
export async function exportOutbounds(params: OutboundParams) { const r = await api.get('/outbounds/files/export.xlsx', { params, responseType: 'blob' }); const u = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = u; a.download = 'Outbound_Export.xlsx'; a.click(); URL.revokeObjectURL(u) }
export async function exportOutboundSelected(ids: number[]) { const r = await api.post('/outbounds/workbench/export-selected', { ids }, { responseType: 'blob' }); const u = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = u; a.download = 'Outbound_Selected.xlsx'; a.click(); URL.revokeObjectURL(u) }

export const updateOutboundTransferCodes = async (ids: number[], transfer_code: string) =>
  (await api.patch('/outbounds/workbench/transfer-code', { ids, transfer_code })).data
export const exportOutboundBols = async (params: Record<string, unknown>, ids?: number[]) => {
  const response = await api.post('/outbounds/workbench/bol-export', { ...params, ids }, { responseType: 'blob' })
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a'); link.href = url; link.download = 'OB_BOL_List.xlsx'
  document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
