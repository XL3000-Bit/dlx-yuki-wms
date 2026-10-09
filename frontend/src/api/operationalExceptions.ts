import { api } from './client'
export type ExceptionStatus='OPEN'|'INVESTIGATING'|'RESOLVED'|'CANCELED'
export interface OperationalException {id:number;exception_no:string;exception_type:string;severity:string;status:ExceptionStatus;title:string;description:string;warehouse_id:number;outbound_id?:number;load_id?:number;container_tracking_id?:number;picking_list_id?:number;bol_id?:number;assigned_to?:number;assigned_team?:string;assignee_name?:string;reported_at:string;resolved_at?:string;resolution?:string;related:Record<string,{id:number;label:string}>;work_orders:{id:number;work_order_no:string;status:string;priority:string}[]}
export const getExceptions=async(params:Record<string,unknown>)=>(await api.get('/operational-exceptions',{params})).data as {data:OperationalException[];meta:{page:number;per_page:number;total:number};counts:Record<string,number>}
export const getException=async(id:number)=>(await api.get(`/operational-exceptions/${id}`)).data as OperationalException
export const getExceptionEvents=async(id:number)=>(await api.get(`/operational-exceptions/${id}/events`)).data
export const createException=async(body:Record<string,unknown>)=>(await api.post('/operational-exceptions',body)).data as OperationalException
export const assignException=async(id:number,body:Record<string,unknown>)=>(await api.post(`/operational-exceptions/${id}/assign`,body)).data as OperationalException
export const transitionException=async(id:number,status:string)=>(await api.post(`/operational-exceptions/${id}/status`,{status})).data as OperationalException
export const resolveException=async(id:number,resolution:string)=>(await api.post(`/operational-exceptions/${id}/resolve`,{resolution})).data as OperationalException
export const createExceptionWorkOrder=async(id:number,body:Record<string,unknown>)=>(await api.post(`/operational-exceptions/${id}/work-orders`,body)).data
