import { api } from './client';
export const bolStatuses = ['Pre', 'Confirmed', 'In Transit', 'Delivered', 'Exception', 'Canceled'];
export const shippingModes = ["53' FTL", 'LTL', "26' FTL", 'Floor loaded', "30' FTL"];
export interface BolDetails {
  carrier_id?: number | null; shipping_mode?: string; payment?: string;
  scheduled_pickup_time?: string | null; delivery_appointment_time?: string | null;
  estimated_transit_days?: number | null;
  [key: string]: string | number | null | undefined;
}
export interface BolLoad {
  id: number; load_id: string; container_number: string; marking: string; delivery_code: string;
  location: string; book_qty: number; actual_qty: number; current_qty: number; weight_lbs: number;
  cbm: number; inbound_pallets: number; whs_pallets: number; shipout_pallets: number; remaining_pallets: number;
  qty?: number; pallets?: number; status?: string;
  receiver_shipment_id?: string; receiver_reference_id?: string; estimate_pallets?: number; markup_pallets?: number;
  remaining_weight_lbs?: number; remaining_cbm?: number; shipped_qty?: number; canceled_qty?: number; canceled_pallets?: number;
}
export interface LoadQuantity { inventory_lot_id: number; pallet_qty: number; carton_qty: number; weight_lbs: number; cbm: number }
export interface PodDocument { id: number; original_filename: string; version: number; status: string; created_at: string }
export interface Shipout { at: string; operator: string; request_id: string; remark: string; lines: LoadQuantity[] }
export interface UniBol {
  id: number; bol_no: string; ob_no: string; status: string; version: number; type: string;
  customer_id: number; customer: string; warehouse_id: number; pickup: string; delivery_code: string;
  created_at: string; updated_at: string; created_by: string; carrier: string; loads_count: number;
  whs_pallets: number; cartons: number; actual_pickup_time?: string; delivery_time?: string; details: BolDetails; loads: BolLoad[];
  documents: { id: number; bol_no: string; status: number }[];
  activities: { action: string; at: string; data: { status: string; version: number } }[];
  group_status: string; pod_status: string; remaining_qty: number; shipped_qty: number;
  pod_documents: PodDocument[];
  workflow: { shipouts?: Shipout[]; cancellations?: Shipout[]; pod_document_id?: number; pod_uploads?: { document_id: number; delivery_date: string; delivery_appointment: string; at: string; operator: string; ob_no?: string }[]; pod_reviews?: { document_id: number; result: string; remark: string; at: string; operator: string }[] };
}
export const getUniBols = async (params: Record<string, unknown>) => (await api.get<{ data: UniBol[]; total: number; counts: Record<string, number> }>('/uni-bols', { params })).data;
export const getUniBol = async (id: number): Promise<UniBol> => (await api.get(`/uni-bols/${id}`)).data;
export const getPodCandidates = async (ob_no: string): Promise<UniBol[]> => (await api.get('/uni-bols/pod-candidates', { params: { ob_no } })).data;
export async function uploadBatchBolPod(selection: { ob_no: string; bols: { id: number; version: number }[]; delivery_date: string; delivery_appointment: string }, file: File): Promise<UniBol[]> {
  const data = new FormData(); data.append('selection', JSON.stringify(selection)); data.append('file', file);
  return (await api.post('/uni-bols/pod-batch', data)).data;
}
export const createUniBol = async (data: unknown): Promise<UniBol> => (await api.post('/uni-bols', data)).data;
export const saveUniBol = async (id: number, version: number, details: BolDetails): Promise<UniBol> => (await api.put(`/uni-bols/${id}`, { version, details })).data;
export const getBolLoads = async (id: number, q: string): Promise<BolLoad[]> => (await api.get(`/uni-bols/${id}/loads`, { params: { q } })).data;
export const selectBolLoads = async (id: number, version: number, lines: LoadQuantity[]): Promise<UniBol> => (await api.post(`/uni-bols/${id}/loads`, { version, lines })).data;
export const actOnBol = async (id: number, version: number, action: string, extra: Record<string, unknown> = {}): Promise<UniBol> => (await api.post(`/uni-bols/${id}/actions`, { version, action, ...extra })).data;
export async function uploadBolPod(id: number, version: number, file: File, metadata?: { delivery_date: string; delivery_appointment: string }): Promise<UniBol> {
  const data = new FormData(); data.append('version', String(version)); data.append('file', file);
  if (metadata) { data.append('delivery_date', metadata.delivery_date); data.append('delivery_appointment', metadata.delivery_appointment); }
  return (await api.post(`/uni-bols/${id}/pod`, data)).data;
}
export const reviewBolPod = async (id: number, version: number, document_id: number, result: string, remark: string): Promise<UniBol> => (await api.post(`/uni-bols/${id}/pod/review`, { version, document_id, result, remark })).data;
export async function previewUniFile(url: string) {
  const popup = window.open('', '_blank');
  try {
    const response = await api.get(url, { responseType: 'blob' });
    const blob = URL.createObjectURL(response.data);
    if (popup) { popup.opener = null; popup.location.href = blob; }
    else { URL.revokeObjectURL(blob); throw new Error('请允许浏览器打开预览窗口'); }
    setTimeout(() => URL.revokeObjectURL(blob), 120000);
  } catch (e) { popup?.close(); throw e; }
}

export const getDispatchBols = async (id: number, pool: boolean, page: number) => (await api.get<{data: UniBol[]; total: number}>(`/uni-bols/dispatch/${id}`, {params: {pool, page, per_page: 10}})).data;
export const changeDispatchBols = async (id: number, action: 'join' | 'remove', bols: {id: number; version: number}[]) => (await api.post(`/uni-bols/dispatch/${id}`, {action, bols})).data;
