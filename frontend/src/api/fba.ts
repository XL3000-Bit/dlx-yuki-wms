import{api}from'./client';import type{FBAAllocation,FBAParams,FBARecord,FBAResponse}from'../types/fba';
export const getFBA=async(params:FBAParams)=>(await api.get<FBAResponse>('/fba',{params})).data;
export const getFBADetail=async(id:number)=>(await api.get<FBARecord>(`/fba/${id}`)).data;
export const createFBA=async(data:Record<string,unknown>)=>(await api.post<FBARecord>('/fba',data)).data;
export const getFBAAllocations=async(id:number)=>(await api.get<FBAAllocation[]>(`/fba/${id}/allocations`)).data;
export const allocateFBA=async(id:number,data:Record<string,unknown>)=>(await api.post<FBAAllocation>(`/fba/${id}/allocate`,data)).data;
export const releaseFBA=async(fbaId:number,allocationId:number,data:Record<string,unknown>)=>(await api.post<FBAAllocation>(`/fba/${fbaId}/allocations/${allocationId}/release`,data)).data;
export const changeFBAStatus=async(id:number,status:number)=>(await api.post<FBARecord>(`/fba/${id}/status`,{status})).data;
export async function exportFBA(params:FBAParams){const r=await api.get('/fba/files/export.xlsx',{params,responseType:'blob'});const u=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=u;a.download='FBA_Export.xlsx';a.click();URL.revokeObjectURL(u)}
