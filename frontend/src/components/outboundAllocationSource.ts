import type { InventoryLot } from '../types/inventory'
import type { FBAAllocation } from '../types/fba'

export type AllocationSource = { kind: 'inventory'; row: InventoryLot } | { kind: 'fba'; row: FBAAllocation }

export function allocationSourceIds(source: AllocationSource): { inventory_lot_id: number; fba_allocation_id?: number } {
  return source.kind === 'fba'
    ? { inventory_lot_id: source.row.inventory_lot_id, fba_allocation_id: source.row.id }
    : { inventory_lot_id: source.row.id }
}
