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
