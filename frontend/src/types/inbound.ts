export type InboundStatus = 0 | 1 | 2 | 3 | 4 | 5 | 6

export interface NamedRef {
  id: number
  code: string
  name: string
}

export interface UserRef {
  id: number
  display_name: string
}

export interface InboundLine {
  id: number
  line_no: number
  fc_code: string
  pallet_qty: string
  carton_qty: string
  weight_lbs: string | null
  cbm: string | null
  location_id: number | null
  note: string | null
}

export interface InboundLineInput {
  line_no: number
  fc_code: string
  pallet_qty: number
  carton_qty: number
  weight_lbs?: number
  cbm?: number
  location_id?: number
  note?: string
}

export interface InboundRecord {
  id: number
  inbound_no: string
  container_number: string
  po_number: string | null
  customer: NamedRef | null
  warehouse: NamedRef
  location: NamedRef | null
  unload_date: string | null
  received_date: string | null
  fc_code: string | null
  marking: string | null
  pallet_qty: string
  carton_qty: string
  weight_lbs: string | null
  cbm: string | null
  status: InboundStatus
  status_name: string
  aging_days: number | null
  remark: string | null
  created_by: UserRef
  created_at: string
  updated_at: string
  inventory_created: boolean
  inventory_lot_id: number | null
  lines: InboundLine[]
}

export interface InboundInput {
  container_number: string
  po_number?: string
  customer_id?: number
  warehouse_id: number
  unload_date?: string
  received_date?: string
  marking?: string
  status: InboundStatus
  remark?: string
  lines: InboundLineInput[]
  // Aggregate and first-line fields remain available for older API consumers.
  fc_code?: string
  pallet_qty?: number
  carton_qty?: number
  weight_lbs?: number
  cbm?: number
  location_id?: number
}

export interface InboundListParams {
  page?: number
  per_page?: number
  q?: string
  container_number?: string
  customer_id?: number
  warehouse_id?: number
  fc_code?: string
  location_id?: number
  status?: InboundStatus
  unload_date_from?: string
  unload_date_to?: string
  received_date_from?: string
  received_date_to?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface InboundListResponse {
  data: InboundRecord[]
  meta: { page: number; per_page: number; total: number; total_pages: number }
}
