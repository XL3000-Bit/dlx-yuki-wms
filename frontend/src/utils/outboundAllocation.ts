import type { FBAAllocation } from '../types/fba'
import type { InventoryLot } from '../types/inventory'
import type { OutboundRecord } from '../types/outbound'
import type { AllocationFormValues, AllocationSelection, AllocationSource, OutboundAllocateRequest, OutboundRemainingSource } from '../types/outboundAllocation'

// Keep decimal text intact; never turn unavailable data into a numeric zero.
export function quantityText(value: unknown): string | null {
  if (typeof value !== 'string' && typeof value !== 'number') return null
  if (typeof value === 'number' && !Number.isFinite(value)) return null
  const text = String(value).trim()
  return /^\d+(?:\.\d+)?$/.test(text) ? text : null
}

function validId(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

export type WorkbenchQuantityField = 'pallet' | 'carton' | 'weight_lbs' | 'cbm'

export function workbenchSourceQuantity(row: OutboundRemainingSource, field: WorkbenchQuantityField): string | null {
  const prefix = row.source_type === 'FBA' ? 'remaining' : row.source_type === 'INVENTORY' ? 'available' : null
  const suffix: Record<WorkbenchQuantityField, string> = {
    pallet: 'pallet_qty',
    carton: 'carton_qty',
    weight_lbs: 'weight_lbs',
    cbm: 'cbm',
  }
  return prefix ? quantityText(row[`${prefix}_${suffix[field]}` as keyof OutboundRemainingSource]) : null
}

export function workbenchSourceError(row: OutboundRemainingSource): string | null {
  if (!validId(row.id) || !validId(row.inventory_lot_id) ||
      (row.source_type === 'FBA' && !validId(row.fba_allocation_id))) {
    return 'Source is missing a valid inventory lot or FBA allocation ID. Refresh the source list.'
  }
  if (row.source_type !== 'FBA' && row.source_type !== 'INVENTORY') return 'Source type is invalid. Refresh the source list.'
  if (['pallet', 'carton', 'weight_lbs', 'cbm'].some(field =>
    workbenchSourceQuantity(row, field as WorkbenchQuantityField) === null)) {
    return 'Source balance is unavailable. Refresh before allocating.'
  }
  return null
}

export function workbenchSourceAllocationData(row: OutboundRemainingSource): OutboundAllocateRequest {
  const error = workbenchSourceError(row)
  if (error) throw new Error(error)
  const request = {
    inventory_lot_id: row.inventory_lot_id,
    pallet_qty: workbenchSourceQuantity(row, 'pallet')!,
    carton_qty: workbenchSourceQuantity(row, 'carton')!,
    weight_lbs: workbenchSourceQuantity(row, 'weight_lbs')!,
    cbm: workbenchSourceQuantity(row, 'cbm')!,
  }
  return row.source_type === 'FBA' ? { ...request, fba_allocation_id: row.fba_allocation_id! } : request
}

export function retainValidSourceSelection(ids: number[], rows: OutboundRemainingSource[], ready: boolean): number[] {
  if (!ready) return []
  const valid = new Set(rows.filter(row => !workbenchSourceError(row)).map(row => row.id))
  return ids.filter(id => valid.has(id))
}

export const FBA_MAPPING_MISSING_MESSAGE = 'FBA source mapping is missing. Open the linked FBA shipment and correct the inventory source mapping, then refresh this list.'
export const FBA_MAPPING_INVALID_MESSAGE = 'FBA source mapping is invalid. Open the linked FBA shipment and correct the inventory source mapping, then refresh this list.'

export type FbaSourceClassification = {
  sources: AllocationSource[]
  mappingError: string | null
}

export function allocationContext(ob: OutboundRecord | null): string {
  return ob ? JSON.stringify([ob.id, ob.ob_type, ob.warehouse.id, ob.fba_shipment?.id ?? null]) : ''
}

export function inventoryAllocationSource(row: InventoryLot, usable: boolean): AllocationSource {
  return { source_type: 'INVENTORY', key: `INVENTORY:${row.id}`, row, inventory_lot_id: row.id,
    quantities: {
      pallet_qty: quantityText(usable ? row.available_pallet_qty : null),
      carton_qty: quantityText(usable ? row.available_carton_qty : null),
      weight_lbs: quantityText(usable ? row.available_weight_lbs : null),
      cbm: quantityText(usable ? row.available_cbm : null),
    } }
}

export function fbaAllocationSource(row: FBAAllocation, sources: OutboundRemainingSource[]): AllocationSource {
  // Both IDs must agree. Missing/fully exhausted sources are not assumed to be zero.
  const matches = sources.filter(source => source.source_type === 'FBA' &&
    source.id === row.id && source.fba_allocation_id === row.id && source.inventory_lot_id === row.inventory_lot_id)
  const remaining = matches.length === 1 ? matches[0] : undefined
  return { source_type: 'FBA', key: `FBA:${row.id}`, row,
    inventory_lot_id: row.inventory_lot_id, fba_allocation_id: row.id,
    quantities: {
      pallet_qty: quantityText(remaining?.remaining_pallet_qty),
      carton_qty: quantityText(remaining?.remaining_carton_qty),
      weight_lbs: quantityText(remaining?.remaining_weight_lbs),
      cbm: quantityText(remaining?.remaining_cbm),
    } }
}

export function classifyFbaAllocationSources(rows: FBAAllocation[], sources: OutboundRemainingSource[]): FbaSourceClassification {
  if (rows.length === 0) {
    return { sources: [], mappingError: sources.length === 0 ? FBA_MAPPING_MISSING_MESSAGE : FBA_MAPPING_INVALID_MESSAGE }
  }

  const mapped: AllocationSource[] = []
  const consumed = new Set<OutboundRemainingSource>()
  for (const row of rows) {
    if (!validId(row.id) || !validId(row.inventory_lot_id)) return { sources: [], mappingError: FBA_MAPPING_INVALID_MESSAGE }
    const exact = sources.filter(source => source.source_type === 'FBA' && source.id === row.id &&
      source.fba_allocation_id === row.id && source.inventory_lot_id === row.inventory_lot_id)
    if (exact.length > 1) return { sources: [], mappingError: FBA_MAPPING_INVALID_MESSAGE }
    if (exact.length === 1) {
      consumed.add(exact[0])
      const adapted = fbaAllocationSource(row, exact)
      if (allocationSourceError(adapted)) return { sources: [], mappingError: FBA_MAPPING_INVALID_MESSAGE }
      mapped.push(adapted)
      continue
    }

    // The workbench omits a fully exhausted source. A related but non-exact row is a broken mapping.
    if (sources.some(source =>
      source.id === row.id || source.fba_allocation_id === row.id || source.inventory_lot_id === row.inventory_lot_id)) {
      return { sources: [], mappingError: FBA_MAPPING_INVALID_MESSAGE }
    }
  }

  if (sources.some(source => !consumed.has(source))) {
    return { sources: [], mappingError: FBA_MAPPING_INVALID_MESSAGE }
  }
  return { sources: mapped, mappingError: null }
}

export function allocationSourceError(source: AllocationSource): string | null {
  if (!validId(source.inventory_lot_id) || (source.source_type === 'FBA' && !validId(source.fba_allocation_id))) {
    return 'Source is missing a valid inventory lot or FBA allocation ID. Refresh the source list.'
  }
  if (Object.values(source.quantities).some(value => value === null)) return 'Source balance is unavailable. Refresh before allocating.'
  return null
}

function exceeds(value: string, limit: string): boolean {
  // Align decimal scales using integers; Number subtraction/comparison loses precision.
  const [whole, fraction = ''] = value.split('.')
  const [limitWhole, limitFraction = ''] = limit.split('.')
  const scale = Math.max(fraction.length, limitFraction.length)
  return BigInt(whole + fraction.padEnd(scale, '0')) > BigInt(limitWhole + limitFraction.padEnd(scale, '0'))
}

export function buildOutboundAllocationRequest(source: AllocationSource | undefined, selection: AllocationSelection | null,
  context: string, values: AllocationFormValues): OutboundAllocateRequest {
  if (!source || !selection || !context || selection.context !== context || selection.key !== source.key) {
    throw new Error('Source selection has changed. Select a source for this Outbound again.')
  }
  const error = allocationSourceError(source)
  if (error) throw new Error(error)
  // Omitted quantities retain the API's explicit zero default; null/invalid input does not.
  const quantities = {
    pallet_qty: quantityText(values.pallet_qty === undefined ? '0' : values.pallet_qty),
    carton_qty: quantityText(values.carton_qty === undefined ? '0' : values.carton_qty),
    weight_lbs: quantityText(values.weight_lbs === undefined ? '0' : values.weight_lbs),
    cbm: quantityText(values.cbm === undefined ? '0' : values.cbm),
  }
  const { pallet_qty, carton_qty, weight_lbs, cbm } = quantities
  if (pallet_qty === null || carton_qty === null || weight_lbs === null || cbm === null) throw new Error('Enter valid non-negative quantities.')
  for (const field of ['pallet_qty', 'carton_qty', 'weight_lbs', 'cbm'] as const) {
    const limit = source.quantities[field]
    const value = quantities[field]
    if (limit === null || value === null || exceeds(value, limit)) throw new Error('Allocation exceeds the current source balance. Refresh and check quantities.')
  }
  if (![pallet_qty, carton_qty, weight_lbs, cbm].some(value => /[1-9]/.test(value))) throw new Error('Enter at least one positive quantity.')
  const request = { pallet_qty, carton_qty, weight_lbs, cbm, inventory_lot_id: source.inventory_lot_id }
  return source.source_type === 'FBA' ? { ...request, fba_allocation_id: source.fba_allocation_id } : request
}
