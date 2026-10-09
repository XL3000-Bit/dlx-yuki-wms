import { api } from './client'
export interface ContainerTrackingRow {
  id: number
  container_number: string
  tracking_status: string
  mbl_number: string | null
  hbl_number: string | null
  pod_eta: string | null
  delivery_warehouse_raw: string | null
  wa_received_at: string | null
  earliest_outbound_date: string | null
  outbound_days_remaining: number | null
  dispatch_priority: string
  inbound_date: string | null
  warehouse_days: number | null
}
export interface ContainerOutboundTask {
  outbound_id: number
  ob_no: string
  fc_code: string | null
  outbound_date: string | null
  pallet_qty: string | number
  completed_pallet_qty: string | number
  status_name: string
  picking_status: number | null
  bol_no: string | null
}
interface ContainerTrackingList {
  data: ContainerTrackingRow[]
  meta: {page: number; per_page: number; total: number; total_pages: number}
}
interface ContainerTrackingDetail {
  basic: ContainerTrackingRow & {dispatch_readiness: string}
  related_outbound_tasks: ContainerOutboundTask[]
}
export const getContainerTrackings=async(params:Record<string,unknown>)=>(await api.get<ContainerTrackingList>('/container-tracking',{params})).data
export const getContainerTracking=async(id:number)=>(await api.get<ContainerTrackingDetail>(`/container-tracking/${id}`)).data
export const importContainerTracking=async(file:File)=>{const f=new FormData();f.append('file',file);return (await api.post<{created:number;updated:number}>('/container-tracking/import',f)).data}
