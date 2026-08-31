# PHASE 11.1 — Picking Scan Workflow

## Status and scope

PHASE 11.1 adds transactional PICK execution to the PHASE 11.0 scan foundation. An operator binds a session to an existing picking list, scans the expected location and inventory lot, and confirms a quantity. The implementation uses the existing picking, allocation, inventory, outbound, RBAC, and audit boundaries.

This phase does not implement STAGE, LOAD_VERIFY, dispatch readiness, POD closure, or any PHASE 11.2 workflow.

## Data model and migration

Migration `20260830_0023_picking_scan_workflow` extends only the scan-execution tables:

- `scan_sessions.current_location_id` records the accepted location step;
- `scan_sessions.current_picking_item_id` records the accepted lot/item step;
- a PostgreSQL partial unique index permits at most one `OPEN` `PICK` session per picking list;
- `scan_events.event_type` distinguishes generic scans, location scans, lot scans, and confirmed picks;
- `scan_events.picking_item_id`, `quantity`, and `quantity_unit` retain the PICK fact;
- `scan_events.client_operation_id` provides per-session confirmation idempotency;
- constraints require positive PICK quantity, a valid unit, and complete PICK event context.

The existing PostgreSQL append-only trigger continues to prevent scan-event updates and deletes. No inventory, allocation, picking, outbound, or PHASE 10 schema is altered. The downgrade removes only these PHASE 11.1 additions and restores the PHASE 11.0 constraints.

## Pick transaction model

`POST /api/v1/scan-sessions/{session_id}/confirm-pick` executes one atomic transaction:

1. lock the scan session;
2. return the original accepted response when the client operation ID already exists;
3. validate the session is open and currently has location plus lot/item context;
4. lock and validate the picking list and picking item;
5. lock and validate the outbound allocation and inventory lot;
6. calculate the executable remainder;
7. increment the existing item picked quantity;
8. advance only the picking-list status when its established rules require it;
9. append an immutable `PICK_CONFIRMED` event;
10. clear the current location/item step and commit everything together.

Any validation failure rolls back the entire transaction. The API never reports success before the picked quantity and audit event are both durable.

## Scan sequence

PICK uses one strict, repeating sequence:

`PICK session -> LOCATION -> LOT -> QUANTITY -> LOCATION -> LOT -> QUANTITY ...`

- A session requires `warehouse_id`, operation `PICK`, and a stable `picking_ref`.
- The picking list infers its outbound context. A supplied outbound reference must identify that same order.
- A location is accepted only when it belongs to the session warehouse and has remaining work on the bound picking list.
- A lot is accepted only when its picking item belongs to the accepted location, its allocation is still valid, and its inventory is pickable.
- Quantity must be positive and cannot exceed the server-computed executable remainder.
- Escape/reset clears the in-progress location/lot step without changing confirmed quantities.

Structured rejection results distinguish sequencing/state errors from `PICK_SOURCE_MISMATCH`. Wrong-warehouse or unauthorized identifiers are not exposed across the existing access boundary.

## Supported identifiers

| Input | Supported value |
| --- | --- |
| Picking context | `PickingList.picking_no` |
| Outbound context | `OutboundOrder.ob_no` (derived from picking) |
| Location scan | `WarehouseLocation.location_code` |
| Source scan | `InventoryLot.lot_no` |

Pallet/LPN and SKU scanning are not supported because no stable entity or identifier exists in the current data model. Quantity fields are not treated as identifiers.

## Inventory and allocation mutation boundary

Allocation already moves stock from available to allocated inventory. PICK confirmation records physical execution only in `PickingListItem.picked_pallet_qty` or `picked_carton_qty`.

PICK deliberately does not change:

- `InventoryLot.available_*`;
- `InventoryLot.allocated_*`;
- `OutboundInventoryAllocation.allocated_*`;
- `OutboundInventoryAllocation.completed_*`;
- `OutboundOrder.status`.

The existing outbound-completion workflow remains the owner of final inventory depletion and allocation completion. This prevents double deduction and preserves API/status compatibility.

## Idempotency and concurrency

- Every quantity submission includes a non-empty client operation ID.
- `(session_id, client_operation_id)` is unique for confirmed PICK events.
- Repeating a successful operation ID returns the original event and current server summary without another increment.
- The session, picking list, item, allocation, and lot are locked with PostgreSQL `FOR UPDATE` before mutation.
- Two different operation IDs racing for the last unit serialize; one succeeds and the other observes the new state and receives a conflict.
- The partial unique open-session index closes the race between two clients attempting to open PICK sessions for the same picking list.

## Picking and outbound statuses

| Condition | Picking result |
| --- | --- |
| First confirmed quantity from `NEW` or `PRINTED` | `IN_PROGRESS` |
| At least one item still has remaining quantity | stays `IN_PROGRESS` |
| Every picking item has no remaining quantity | `COMPLETED` |
| Existing `COMPLETED`, `CANCELED`, or `EXCEPTION` | PICK session/confirmation rejected |

Scan-session `COMPLETED` and `CANCELED` are session terminal states only. They never roll back accepted picks and do not falsely complete a partial picking list. Outbound status is unchanged throughout this workflow.

## API

The existing `/api/v1/scan-sessions` surface remains backward compatible. PHASE 11.1 adds:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/{session_id}/confirm-pick` | Confirm a positive quantity with a client operation ID. |
| `POST` | `/{session_id}/reset-step` | Clear current location/lot context only. |

Session create/read/scan responses now include an optional PICK summary: picking/outbound references, server-selected unit, required/picked/remaining totals, current item/source context, and picking status. Non-PICK PHASE 11.0 clients can ignore these additive fields.

## Scan Workbench PICK mode

The existing `/scan-execution` page provides:

- warehouse plus picking-reference binding, with outbound shown from server context;
- a large autofocus keyboard-wedge field for location and lot scans;
- Enter submission and Escape step reset/focus restoration;
- a quantity entry shown only after a valid lot step;
- server-derived expected step, unit, remaining quantity, status, and progress;
- immutable event history including location, lot, and confirmed quantity facts;
- retry-safe client operation IDs;
- explicit session complete/cancel controls.

The frontend does not recalculate pick availability, inventory mutation, picking completion, or outbound status.

## Permissions and audit

- Existing scan-session warehouse/customer scopes and ownership checks still apply.
- PICK mutation requires the existing outbound-management permission.
- No role, permission name, route family, or authentication rule is added.
- Each accepted and rejected scan remains visible in the append-only event trail.
- Each confirmed quantity records item, quantity, unit, operation ID, operator/session, and timezone-aware event time.

## Acceptance coverage

Backend tests cover stable reference binding, outbound inference, duplicate open-session rejection, mismatched outbound context, terminal picking states, strict location/lot order, wrong location/source, unavailable inventory, single/partial/full picking, over-pick rejection, operation-ID idempotency, multiple picking items, session completion/cancellation, and the inventory/allocation/outbound mutation boundary.

`backend/scripts/phase11_1_postgres_smoke.py` creates and removes an isolated schema in the configured PostgreSQL database. It validates:

- fresh migration to head and clean Alembic drift check;
- `0023 -> 0022 -> 0023` round trip;
- single pick;
- partial then full pick;
- over-pick rejection;
- repeated operation-ID idempotency;
- two-client final-unit concurrency under real PostgreSQL row locks;
- unchanged inventory, allocation, and outbound facts after PICK.

Pass `--keep-schema` only when a temporary fixture is needed for manual browser verification; the default command cleans up its schema.

## Acceptance result

PHASE 11.1 was validated against the configured local PostgreSQL database and the production frontend build:

- Alembic head is `20260830_0023` and `alembic check` reports no drift.
- Fresh PostgreSQL migration from base to head passed.
- The `0023 -> 0022 -> 0023` downgrade/upgrade round trip passed.
- The PostgreSQL smoke scenarios passed for single, partial, full, over-pick, duplicate-submit, and concurrent final-unit execution.
- The full backend suite passed all 135 collected tests; the focused Scan Execution suite passed all 16 tests.
- Python compilation and the frontend TypeScript/production build passed.
- Manual browser smoke passed against the isolated PostgreSQL fixture. Warehouse, picking, location, lot, and quantity were entered through the real Scan Workbench; Enter advanced each scan step, Escape reset the active step without mutation, a quantity of two completed the picking list, and completing the scan session preserved the accepted pick and event history.
- The browser flow left the outbound order and inventory/allocation quantities unchanged, as required by the PICK mutation boundary.
- The temporary PostgreSQL smoke schema was removed after validation.

## Known limitations

- The current model has no stable pallet/LPN, SKU, serial, or carton barcode.
- Quantity confirmation is numeric and item-based; it is not physical pallet identity capture.
- One PICK session is exclusive per picking list; collaborative multi-operator picking is not modeled.
- A completed/canceled scan session does not create a compensating pick rollback workflow.
- Offline queues, device identity, camera scanning, and mobile-specific UX are not implemented.
- Operational time uses the configured global business timezone; per-warehouse timezones are not supported.
- STAGE and LOAD_VERIFY remain foundation-only operation values with no PHASE 11.1 execution workflow.
