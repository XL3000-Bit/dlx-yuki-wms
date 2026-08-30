import { api } from './client'
export const getContainerTrackings=async(params:Record<string,unknown>)=>(await api.get('/container-tracking',{params})).data
export const getContainerTracking=async(id:number)=>(await api.get(`/container-tracking/${id}`)).data
export const importContainerTracking=async(file:File)=>{const f=new FormData();f.append('file',file);return (await api.post('/container-tracking/import',f)).data}
