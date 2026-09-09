import { api } from './client'
import type {
  InboundInput,
  InboundListParams,
  InboundListResponse,
  InboundRecord,
} from '../types/inbound'
import type { InventoryLot } from '../types/inventory'

export interface ReceiveInboundResponse {
  inbound: InboundRecord
  inventory_lots: InventoryLot[]
}

export const getInbounds = async (params: InboundListParams) =>
  (await api.get<InboundListResponse>('/inbound', { params })).data

export const getInbound = async (id: number) =>
  (await api.get<InboundRecord>(`/inbound/${id}`)).data

export const createInbound = async (data: InboundInput) =>
  (await api.post<InboundRecord>('/inbound', data)).data

export const updateInbound = async (id: number, data: InboundInput) =>
  (await api.patch<InboundRecord>(`/inbound/${id}`, data)).data

export const receiveInbound = async (id: number) =>
  (await api.post<ReceiveInboundResponse>(`/inbound/${id}/receive`)).data

export const cancelInbound = async (id: number) =>
  (await api.post<InboundRecord>(`/inbound/${id}/cancel`)).data

export async function downloadInbound(
  path: 'template' | 'export',
  params?: InboundListParams,
) {
  const response = await api.get(`/inbound/files/${path}.xlsx`, {
    params,
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const a = document.createElement('a')
  a.href = url
  a.download = path === 'template' ? 'Inbound_Import_Template.xlsx' : 'Inbound_Export.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}
