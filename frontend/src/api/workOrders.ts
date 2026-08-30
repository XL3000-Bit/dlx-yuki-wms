import { api } from './client'
export type WorkOrder={id:number;work_order_no:string;work_order_type:string;status:string;warehouse_id:number;load_id?:number|null;outbound_id?:number|null;picking_list_id?:number|null;priority:string;assigned_to?:number|null;assigned_team?:string|null;assignee_name?:string|null;scheduled_at?:string|null;started_at?:string|null;completed_at?:string|null;created_at:string;notes?:string|null}
export async function getWorkOrders(params:Record<string,unknown>={}){return (await api.get<{data:WorkOrder[];meta:any}>('/work-orders',{params})).data}
export async function getWorkOrder(id:number){return (await api.get<WorkOrder>(`/work-orders/${id}`)).data}
export async function createWorkOrder(payload:Record<string,unknown>){return (await api.post<WorkOrder>('/work-orders',payload)).data}
export async function changeWorkOrderStatus(id:number,status:string){return (await api.post<WorkOrder>(`/work-orders/${id}/status`,{status})).data}
