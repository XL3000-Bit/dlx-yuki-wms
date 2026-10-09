import { api } from './client'

export type CargoBol = {
  id: number; bol_no: string; source_no: string; source_type: string
  warehouse_id: number; customer_id?: number; fba_shipment_id?: number
  po_number?: string; container_number?: string; warehouse_name?: string; customer_name?: string
  del_code?: string; lot_no?: string; historical: boolean; can_allocate: boolean; status_name: string
  available_pallet_qty: number | string; available_carton_qty: number | string
  available_weight_lbs: number | string; available_cbm: number | string
  actual_inbound_date?: string; appointment_time?: string; redirect_code?: string; transfer_code?: string
  outbounds?: { id: number; allocation_id: number; ob_no: string; allocated_pallet_qty: number | string; allocated_carton_qty: number | string; completed_pallet_qty: number | string }[]
}
export type CargoBolFilters = { q?: string; warehouse_id?: number; customer_id?: number; source_type?: string; del_code?: string; remaining_only?: boolean }
export async function getCargoBols(params: CargoBolFilters & { page: number; page_size: number }) {
  return (await api.get<{ data: CargoBol[]; meta: { total: number; totals: Record<string, number | string> } }>('/cargo-bols', { params })).data
}
export async function getCargoBol(id: number) {
  return (await api.get<CargoBol>(`/cargo-bols/${id}`)).data
}
export async function assignCargoBols(outbound_id: number, bol_ids: number[]) {
  return (await api.post<{ ob_no: string; bol_count: number }>('/cargo-bols/assign', { outbound_id, bol_ids })).data
}
export async function createOutboundFromCargo(outbound: Record<string, unknown>, bol_ids: number[]) {
  return (await api.post<{ ob_id: number; ob_no: string; bol_count: number }>('/cargo-bols/create-outbound', { outbound, bol_ids })).data
}
export async function exportCargoBols(params: CargoBolFilters) {
  try {
    const response = await api.get('/cargo-bols/export.xlsx', { params, responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a'); link.href = url; link.download = 'Cargo_BOL_Export.xlsx'; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error: any) {
    if (error.response?.data instanceof Blob) {
      try { throw new Error(JSON.parse(await error.response.data.text()).detail || '导出失败') }
      catch (parsed) { if (parsed instanceof SyntaxError) throw error; throw parsed }
    }
    throw error
  }
}
