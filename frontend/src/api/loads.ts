import { api } from './client'
import type { OperationalException } from './operationalExceptions'
export type Load = { id:number; load_no:string; warehouse_id:number; warehouse?:{code:string;name:string}; carrier?:{code:string;name:string}|null; status:string; appointment_reference?:string|null; appointment_time?:string|null; destination_name?:string|null; destination_address?:string|null; outbound_count:number; outbounds?:any[]; work_orders?:any[]; active_exception_count:number; active_exceptions:Pick<OperationalException,'id'|'exception_no'|'severity'|'status'|'title'>[]; total_pallet_qty:string|number; total_carton_qty:string|number; total_weight_lbs:string|number; total_cbm:string|number; created_at:string; updated_at:string }
export async function getLoads(params:Record<string,unknown>={}) { return (await api.get<{data:Load[];meta:any}>('/loads',{params})).data }
export async function getLoad(id:number) { return (await api.get<Load>(`/loads/${id}`)).data }
export async function createLoad(payload:Record<string,unknown>) { return (await api.post<Load>('/loads',payload)).data }
