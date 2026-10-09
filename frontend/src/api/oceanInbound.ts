import { api } from './client';
import type { InboundRecord } from '../types/inbound';

export interface Receipt {
  version: number;
  expected_qty: string;
  expected_pallets: string;
  received_qty?: string | null;
  inbound_pallets?: string | null;
  location_id?: number | null;
  estimated_pallets?: string | null;
  markup_pallets?: string | null;
  load_type?: 'FBA' | 'FBM' | null;
  memo?: string;
  feedback?: string;
  confirmed_date?: string;
}
export interface OceanLine {
  inbound: InboundRecord;
  receipt: Receipt;
  cargo_bol_no: string | null;
  editable: boolean;
  can_putaway?: boolean;
  inventory?: { id: number; current_qty: string; whs_pallets: string; shipout_pallets: string; remaining_pallets: string; reserved_pallets: string; available_qty: string; reserved_qty: string } | null;
}
export interface ShipmentMetadata {
  version: number; transport_status: string; scheduled_delivery_date?: string | null; pod_eta?: string | null;
  appointment?: string; size?: string; trucker?: string; container_status?: string; team?: string;
  released?: boolean; printed?: boolean; empty_reported?: boolean; outbound_fully_pod?: boolean;
  list_status?: string | null; ir_eta?: string | null; urgent?: boolean; trouble_status?: string; trouble_count?: number;
  terminal_ready_date?: string | null; unloading_amount?: string | null; unloading_remark?: string; operator?: string;
}
export const transportStatuses = ['TBD', '待提待拆', '可提未提', '已提待拆', '在拆', '已提已拆'];
export interface OceanShipment { data: OceanLine[]; can_upload: boolean; grouping: string; shipment: ShipmentMetadata }
export const getOceanInbound = async (id: number): Promise<OceanShipment> =>
  (await api.get(`/ocean-inbound/${id}`)).data;
export async function saveOceanInbound(id: number, rows: OceanLine[], confirm: boolean): Promise<OceanShipment> {
  const lines = rows.map(({ inbound, receipt: r }) => ({
    id: inbound.id, version: r.version, received_qty: r.received_qty ?? null,
    inbound_pallets: r.inbound_pallets ?? null, location_id: r.location_id ?? null,
    estimated_pallets: r.estimated_pallets ?? null, markup_pallets: r.markup_pallets ?? null,
    load_type: r.load_type ?? null, memo: r.memo ?? '', feedback: r.feedback ?? '',
  }));
  return (await api.request({ url: `/ocean-inbound/${id}/${confirm ? 'confirm' : 'draft'}`, method: confirm ? 'POST' : 'PUT', data: { lines } })).data;
}

export interface OceanListRow { id: number; container_number: string; warehouse_id: number; unload_date: string | null; loads_count: number; pieces: string; status: number; putaway_count: number; shipment: ShipmentMetadata }
export const saveOceanShipment = async (id: number, data: Pick<ShipmentMetadata, 'version'> & Partial<ShipmentMetadata>): Promise<OceanShipment> => (await api.put(`/ocean-inbound/${id}/shipment`, data)).data;
export const getOceanShipments = async (params: Record<string, unknown>): Promise<{data: OceanListRow[]; total: number; counts: Record<string, number>; options: Record<string, string[]>}> => (await api.get('/ocean-inbound', { params })).data;
export const putawayOceanInbound = async (id: number, rows: OceanLine[]): Promise<OceanShipment> => (await api.post(`/ocean-inbound/${id}/putaway`, {lines: rows.map(r => ({id: r.inbound.id, version: r.receipt.version}))})).data;
