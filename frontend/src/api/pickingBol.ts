import{api}from'./client';export const getPickings=async()=>(await api.get('/picking-lists')).data;export const generatePicking=async(id:number)=>(await api.post(`/outbounds/${id}/picking-lists`)).data;export const completePicking=async(id:number)=>(await api.post(`/picking-lists/${id}/complete`,{})).data;export const getBols=async()=>(await api.get('/bols')).data;export const generateBol=async(id:number)=>(await api.post(`/outbounds/${id}/bol`)).data;export const ensureOutboundDocuments=async(id:number)=>(await api.post(`/outbounds/${id}/documents/ensure`)).data;export async function downloadFile(url:string,name:string){const r=await api.get(url,{responseType:'blob'});const u=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u)}
export async function downloadOutboundPackage(id: number, obNo: string) {
  try {
    const response = await api.post(`/outbounds/${id}/documents/package`, {}, { responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${obNo}-BOL-抓货单.zip`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (error: any) {
    let detail = '单据生成失败，请重试';
    if (error.response?.data instanceof Blob) {
      try { detail = JSON.parse(await error.response.data.text()).detail || detail; } catch { /* Keep fallback. */ }
    }
    throw new Error(detail);
  }
}
