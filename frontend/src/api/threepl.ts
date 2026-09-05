import { api } from './client'

export interface ThreePLClient {
  customer_id:number; customer_code:string; customer_name:string; contact_name:string|null; email:string|null; is_active:boolean
  inventory_pallets:number; inventory_cartons:number; inventory_cbm:number; hold_pallets:number
  open_inbounds:number; open_outbounds:number; completed_inbounds:number; completed_outbounds:number
  oldest_inventory_days:number|null; last_activity_at:string|null
}
export interface ThreePLOverview {
  meta:{generated_at:string;date_from:string;date_to:string;customer_id:number|null;warehouse_id:number|null;storage_basis:string}
  summary:{active_clients:number;inventory_pallets:number;inventory_cartons:number;inventory_cbm:number;hold_pallets:number;open_inbounds:number;open_outbounds:number}
  usage:{receiving_orders:number;receiving_pallets:number;receiving_cartons:number;outbound_orders:number;outbound_pallets:number;outbound_cartons:number;storage_pallet_days:number}
  clients:ThreePLClient[]
  attention:{severity:'HIGH'|'MEDIUM'|'LOW';customer_id:number;customer_code:string;title:string;detail:string;target:string}[]
}
export const getThreePLOverview=async(params:{date_from:string;date_to:string;customer_id?:number;warehouse_id?:number})=>(await api.get<ThreePLOverview>('/3pl/overview',{params})).data

export interface ThreePLDispatchTask {
  id:number; reference:string; customer_id:number|null; customer_code:string; customer_name:string
  warehouse_id:number; warehouse_code:string; status:number; status_name:string
  priority:'URGENT'|'HIGH'|'NORMAL'|'LOW'; priority_reason:string; queue_state:'READY'|'AT_RISK'|'BLOCKED'
  due_at:string|null; is_overdue:boolean; owner_name:string|null
  work_order_id:number|null; work_order_no:string|null; work_order_type:string|null
  exception_id:number|null; exception_no:string|null; exception_severity:string|null
  picking_id:number|null; picking_no:string|null; picking_status:number|null; picking_status_name:string|null
  bol_id:number|null; bol_no:string|null; bol_status:number|null; bol_status_name:string|null
  document_state:'READY'|'PARTIAL'|'MISSING'
  blocker_code:string|null; blocker_label:string|null; blocker:string|null; carrier_name:string|null
  action_target:string; action_allowed:boolean; action_disabled_reason:string|null
  picking_download_url:string|null; bol_download_url:string|null; updated_at:string
}
export interface ThreePLDispatchQueue {
  generated_at:string; summary_scope:'FILTERED_RESULT'
  summary:{total:number;ready:number;at_risk:number;blocked:number;overdue:number;unassigned:number}
  page:number; page_size:number; total:number; pages:number; sort:string
  tasks:ThreePLDispatchTask[]
}
export interface ThreePLDispatchParams {
  customer_id?:number; warehouse_id?:number; status?:number; readiness?:string; blocker?:string
  priority?:string; search?:string; date_from?:string; date_to?:string
  page:number; page_size:number; sort:string
}
export const getThreePLDispatchQueue=async(params:ThreePLDispatchParams)=>(await api.get<ThreePLDispatchQueue>('/3pl/dispatch-queue',{params})).data
