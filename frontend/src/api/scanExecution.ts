import { api } from "./client";

export type ScanOperationType = "PICK" | "STAGE" | "LOAD_VERIFY";
export type ScanSessionStatus = "OPEN" | "COMPLETED" | "CANCELED";
export type ScanResult =
  | "ACCEPTED"
  | "REJECTED"
  | "DUPLICATE"
  | "NOT_FOUND"
  | "WRONG_WAREHOUSE"
  | "WRONG_OUTBOUND"
  | "WRONG_LOCATION"
  | "PICK_SOURCE_MISMATCH"
  | "INVALID_STATE";

export type PickStep = "EXPECT_LOCATION" | "EXPECT_LOT" | "EXPECT_QUANTITY_CONFIRMATION" | "COMPLETED";
export type PickQuantityUnit = "PALLET" | "CARTON";

export interface ScanSessionCreate {
  warehouse_id: number;
  operation_type: ScanOperationType;
  outbound_id?: number;
  picking_id?: number;
  picking_ref?: string;
  load_id?: number;
}

export interface ScanSession {
  id: number;
  session_no: string;
  warehouse_id: number;
  operation_type: ScanOperationType;
  user_id: number;
  outbound_id: number | null;
  picking_id: number | null;
  load_id: number | null;
  current_location_id: number | null;
  current_picking_item_id: number | null;
  status: ScanSessionStatus;
  last_scan_at: string | null;
  completed_at: string | null;
  canceled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScanCounters {
  total: number;
  accepted: number;
  duplicate: number;
  rejected: number;
  result_counts: Record<string, number>;
}

export interface ScanEvent {
  id: number;
  session_id: number;
  raw_value: string;
  normalized_value: string;
  scan_type: string;
  event_type: string;
  result: ScanResult;
  client_operation_id: string | null;
  matched_entity_type: string | null;
  matched_entity_id: number | null;
  location_id: number | null;
  picking_item_id: number | null;
  quantity: number | null;
  quantity_unit: PickQuantityUnit | null;
  reference_value: string | null;
  message: string;
  scanned_by: number;
  scanned_at: string;
}

export interface PickingExecutionSummary {
  picking_no: string;
  outbound_no: string;
  picking_status: string;
  current_step: PickStep;
  quantity_unit: PickQuantityUnit;
  required_qty: number;
  picked_qty: number;
  remaining_qty: number;
  current_location_code: string | null;
  current_lot_no: string | null;
  current_item_required_qty: number | null;
  current_item_picked_qty: number | null;
  current_item_remaining_qty: number | null;
  current_item_available_qty: number | null;
  locations_visited: number;
  lots_picked: number;
}

export interface ScanSessionResponse {
  session: ScanSession;
  counters: ScanCounters;
  picking_summary: PickingExecutionSummary | null;
}

export interface ScanEventListResponse {
  data: ScanEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface ScanResultResponse extends ScanSessionResponse {
  event: ScanEvent;
  recent_events: ScanEvent[];
}

export async function createScanSession(payload: ScanSessionCreate) {
  return (await api.post<ScanSessionResponse>("/scan-sessions", payload)).data;
}

export async function getScanSession(sessionId: number) {
  return (await api.get<ScanSessionResponse>(`/scan-sessions/${sessionId}`)).data;
}

export async function getScanEvents(sessionId: number, limit = 20) {
  return (
    await api.get<ScanEventListResponse>(`/scan-sessions/${sessionId}/events`, {
      params: { limit, offset: 0 },
    })
  ).data;
}

export async function submitScan(sessionId: number, value: string) {
  return (
    await api.post<ScanResultResponse>(`/scan-sessions/${sessionId}/scan`, {
      value,
    })
  ).data;
}

export async function confirmPick(
  sessionId: number,
  payload: { quantity: number; client_operation_id: string },
) {
  return (
    await api.post<ScanResultResponse>(`/scan-sessions/${sessionId}/confirm-pick`, payload)
  ).data;
}

export async function resetPickStep(sessionId: number) {
  return (
    await api.post<ScanSessionResponse>(`/scan-sessions/${sessionId}/reset-step`)
  ).data;
}

export async function completeScanSession(sessionId: number) {
  return (await api.post<ScanSessionResponse>(`/scan-sessions/${sessionId}/complete`)).data;
}

export async function cancelScanSession(sessionId: number) {
  return (await api.post<ScanSessionResponse>(`/scan-sessions/${sessionId}/cancel`)).data;
}
