# Current Picking Execution Assessment

## Scope and baseline

This assessment records the picking model that PHASE 11.1 extends. The frozen PHASE 10 release-candidate baseline is `f888a2a`; PHASE 11.0 adds append-only scan sessions/events and is retained unchanged. PHASE 11.1 implements only the `PICK` operation. It does not implement staging, load verification, dispatch readiness, POD, or PHASE 11.2 behavior.

## Existing picking model

- `PickingList` is the executable document for one `OutboundOrder`. `picking_no` is a stable, unique operational reference.
- `PickingListItem` is the quantity execution record. Every item points to one `OutboundInventoryAllocation`, one `InventoryLot`, and its expected `WarehouseLocation`.
- The item already stores planned and picked pallet/carton quantities. No second picking fact table is needed.
- `OutboundInventoryAllocation` reserves inventory during allocation. Its allocated/completed quantities belong to the outbound allocation and completion lifecycle, not the physical PICK confirmation step.
- `InventoryLot.available_*` and `allocated_*` quantities are changed during allocation/release. Completing the outbound owns final inventory depletion.

The safest real PICK mutation is therefore to increment the existing `PickingListItem.picked_pallet_qty` or `picked_carton_qty`. PICK must not deduct the same inventory a second time, complete the allocation, or complete the outbound.

## Quantity unit selection

The current schema has no stable pallet/LPN entity and no SKU master. A picking item is executed in:

- `PALLET` when its planned pallet quantity is greater than zero;
- otherwise `CARTON` when its planned carton quantity is greater than zero.

The workflow does not invent pallet, LPN, SKU, serial, or carton identifiers. Quantity is entered only after the expected location and inventory lot have been accepted.

## Existing lifecycle boundary

- `NEW` and `PRINTED` picking lists can start PICK execution and become `IN_PROGRESS` after the first confirmed quantity.
- `IN_PROGRESS` lists can continue execution.
- A picking list becomes `COMPLETED` only when every item has no remaining executable quantity.
- `COMPLETED`, `CANCELED`, and `EXCEPTION` picking lists cannot open or continue a PICK session.
- Completing or canceling a scan session does not roll back already confirmed quantities.
- A partially executed session can be completed without claiming that its picking list or outbound is complete.
- The `OutboundOrder` status is intentionally unchanged by PICK confirmation.

## Supported identifiers

PHASE 11.1 uses exact, case-insensitive matching of existing stable references only:

| Purpose | Identifier | Scope rule |
| --- | --- | --- |
| Session binding | `PickingList.picking_no` | Resolves through its outbound and warehouse. |
| Derived context | `OutboundOrder.ob_no` | Inferred from the picking list; an explicit value must match. |
| First scan | `WarehouseLocation.location_code` | Must belong to the session warehouse and an unfinished picking item. |
| Second scan | `InventoryLot.lot_no` | Must match an unfinished item at the accepted location. |

## Required scan sequence

The operational sequence is deliberately strict:

1. Create an open `PICK` session bound to a warehouse and picking reference.
2. Scan the expected location.
3. Scan the expected inventory lot.
4. Enter and confirm a positive quantity in the server-selected unit.
5. Repeat location, lot, and quantity until work is finished or the operator terminates the session.

A lot before a location, the wrong lot for the accepted location, a stale source, an unavailable lot, an over-pick, or a terminal picking state is rejected without quantity mutation. Reset clears only the current location/lot step.

## Transaction and concurrency requirements

One confirmation transaction must lock and revalidate the scan session, picking list, picking item, outbound allocation, and inventory lot. The permitted quantity is bounded by all three remaining facts:

- picking-item remaining quantity;
- allocation quantity not yet completed by the outbound lifecycle;
- lot quantity still allocated.

The database permits at most one open PICK session per picking list. A client-generated operation ID is unique within a session, making a retry return the original accepted event instead of incrementing quantity twice. Row locks serialize distinct operation IDs competing for the same remaining quantity.

## PHASE 11.1 implementation path

1. Extend the PHASE 11.0 session with current location/item context.
2. Extend append-only scan events with structured PICK event type, item, quantity, unit, and client operation ID.
3. Add a focused `confirm-pick` transaction and reset-step action to the existing scan service/API.
4. Reuse the Scan Workbench in PICK mode with a server-driven state summary.
5. Verify unit behavior, real PostgreSQL constraints/row locks, migration round trips, frontend build, and a keyboard-only browser smoke.

## Explicit non-goals

- No pallet/LPN, SKU, serial, or barcode master-data creation.
- No second inventory deduction during PICK.
- No allocation completion or outbound status transition during PICK.
- No scan-driven STAGE or LOAD_VERIFY execution.
- No camera/mobile scanner, offline queue, or device management.
- No dispatch readiness or PHASE 11.2 behavior.
