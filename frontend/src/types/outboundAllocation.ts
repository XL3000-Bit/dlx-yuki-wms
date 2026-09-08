import type { FBAAllocation } from './fba'
import type { InventoryLot } from './inventory'

export type QuantityField = 'pallet_qty' | 'carton_qty' | 'weight_lbs' | 'cbm'
export type AllocationQuantities = Record<QuantityField, string>
export type AllocationFormValues = Partial<Record<QuantityField, unknown>>

// Consumed subset of the existing workbench-detail response (not FBAAllocation).
export type OutboundRemainingSource = {
  id: number
  inventory_lot_id: number
  fba_allocation_id: number | null
  source_type: 'FBA' | 'INVENTORY'
  lot_no?: string | null
  container_number?: string | null
  fc_code?: string | null
  location?: string | null
  inbound_date?: string | null
  warehouse_days?: number | null
  earliest_outbound_date?: string | null
  outbound_days_remaining?: number | null
  dispatch_priority?: string | null
  available_pallet_qty?: string | number | null
  available_carton_qty?: string | number | null
  available_weight_lbs?: string | number | null
  available_cbm?: string | number | null
  remaining_pallet_qty?: string | number | null
  remaining_carton_qty?: string | number | null
  remaining_weight_lbs?: string | number | null
  remaining_cbm?: string | number | null
}
export type OutboundAllocationSources = {
  basic: { id: number; ob_type: string; fba_id: number | null }
  remaining_sources: OutboundRemainingSource[]
  allowed_actions: { allocate: boolean }
}

type SourceBalance = { key: string; quantities: Record<QuantityField, string | null> }
export type AllocationSource = SourceBalance & (
  | { source_type: 'INVENTORY'; row: InventoryLot; inventory_lot_id: number }
  | { source_type: 'FBA'; row: FBAAllocation; inventory_lot_id: number; fba_allocation_id: number }
)
export type AllocationSelection = { context: string; key: string }
export type OutboundAllocateRequest = AllocationQuantities & (
  | { inventory_lot_id: number; fba_allocation_id?: never }
  | { inventory_lot_id: number; fba_allocation_id: number }
)
