export type FBAWorkbenchStage =
  | "all"
  | "waiting_picking"
  | "waiting_appointment"
  | "waiting_outbound"
  | "dispatched"
  | "completed"
  | "exception";
export interface FBAWorkbenchParams {
  page: number;
  per_page: number;
  warehouse_id?: number;
  customer_id?: number;
  q?: string;
  stage: FBAWorkbenchStage;
  priority?: string;
  only_old?: boolean;
  unload_from?: string;
  unload_to?: string;
  aging_min?: number; aging_max?: number; amazon_fc_code?: string; container_number?: string; location_id?: number; carrier_id?: number; fba_status?: number; outbound_status?: number; picking_status?: number; bol_status?: number; st_number?: string; po_number?: string; scheduled_from?: string; scheduled_to?: string; appointment_from?: string; appointment_to?: string;
  sort_by: string;
  sort_order: "asc" | "desc";
}
export interface FBAWorkbenchRow {
  id: number;
  fba_no: string;
  shipment_id: string | null;
  st_number: string | null;
  po_number: string | null;
  reference_no: string | null;
  customer: string | null;
  warehouse_id: number;
  warehouse: string;
  amazon_fc_code: string;
  amazon_fc_name: string | null;
  fc_address_missing: boolean;
  container_count: number;
  containers_preview: string[];
  location_count: number;
  locations_preview: string[];
  total_pallet_qty: string;
  total_carton_qty: string;
  total_weight_lbs: string;
  total_cbm: string;
  oldest_inbound_date: string | null;
  max_aging_days: number | null;
  priority_level: string | null;
  priority_label: string | null;
  priority_range: string | null;
  priority_rank: number;
  inbound_date: string | null;
  warehouse_days: number | null;
  earliest_outbound_date: string | null;
  outbound_days_remaining: number | null;
  dispatch_priority: "CRITICAL" | "HIGH" | "MEDIUM" | "NORMAL";
  dispatch_priority_rank: number;
  appointment_time: string | null;
  scheduled_pickup_at: string | null;
  picking_count: number;
  picking_id: number | null;
  picking_no: string | null;
  picking_status: number | null;
  bol_id: number | null;
  bol_no: string | null;
  bol_status: number | null;
  outbound_id: number | null;
  outbound_no: string | null;
  outbound_status: number | null;
  workbench_stage: Exclude<FBAWorkbenchStage, "all">;
  workbench_stage_name: string;
  has_exception: boolean;
  status: number;
  created_at: string;
  updated_at: string;
}
export interface FBASummary {
  task_count: number;
  total_pallet_qty: string;
  total_carton_qty: string;
  total_weight_lbs: string;
  total_cbm: string;
  average_aging_days: number | null;
}
export interface FBAStageCounts {
  all: number;
  waiting_picking: number;
  waiting_appointment: number;
  waiting_outbound: number;
  dispatched: number;
  completed: number;
  exception: number;
}
export interface FBAWorkbenchResponse {
  data: FBAWorkbenchRow[];
  meta: {
    page: number;
    per_page: number;
    total: number;
    total_pages: number;
    attention_threshold_days: number;
    trailer_default_pallet_capacity: number;
  };
  summary: FBASummary;
  stage_counts: FBAStageCounts;
  permissions: { can_export: boolean; can_operate: boolean };
}
export interface FBAWorkflowStep {
  key: string;
  label: string;
  status: "completed" | "current" | "pending" | "exception";
}
export interface FBAWorkbenchDetail {
  basic: Record<string, unknown>;
  inventory_sources: Array<Record<string, unknown>>;
  picking: Array<Record<string, unknown>>;
  bol: Record<string, unknown> | null;
  outbound: Record<string, unknown> | null;
  audit: Array<{
    time: string;
    user: string;
    action: string;
    entity: string;
    detail: unknown;
  }>;
  workflow: FBAWorkflowStep[];
  permissions: { can_export: boolean; can_operate: boolean };
}
