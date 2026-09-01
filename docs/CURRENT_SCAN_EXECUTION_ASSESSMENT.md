# Current Scan Execution Assessment

## Scope and baseline

This assessment records the pre-PHASE 11.0 implementation state at the frozen PHASE 10 release-candidate baseline (`f888a2a`). PHASE 11.0 adds scan capture, validation, and audit history only. It does not execute inventory movements, quantity completion, picking transitions, loading transitions, or outbound lifecycle transitions.

## Existing execution entities

- `OutboundOrder` is the outbound aggregate. `ob_no` is globally unique and indexed. It owns inventory allocations, can reference one FBA shipment and one load, and carries the existing outbound status machine.
- `OutboundInventoryAllocation` links an outbound order to an `InventoryLot` and stores allocated/completed quantities. The pair `(outbound_order_id, inventory_lot_id)` is unique.
- `InventoryLot` is the stable inventory source record. `lot_no` is globally unique and indexed. `container_number` is indexed but is not unique because one physical/logical container can produce multiple lots.
- `InventoryLotLocation` and `WarehouseLocation` represent inventory placement. `location_code` is unique only within a warehouse.
- `PickingList` is linked to one outbound order. `picking_no` is globally unique and indexed. Its items identify the allocation, inventory lot, and expected location.
- `FBAShipment` uses globally unique, indexed `fba_no`. Other FBA references (`shipment_id`, `st_number`, `reference_no`, and `source_reference`) are searchable but are not unique.
- `Load` uses globally unique, indexed `load_no` and is warehouse-scoped.
- `WorkOrder` and `OperationalException` already provide execution coordination and exception history, but neither stores raw scan input.

## Existing relationships and lifecycle boundaries

- Inventory availability is represented by `InventoryLot` plus `InventoryLotLocation`; outbound demand reaches that inventory only through `OutboundInventoryAllocation`.
- Picking execution is `OutboundOrder -> PickingList -> PickingListItem`, with each item retaining its allocation, lot, expected location, and quantity context.
- The existing outbound, picking, load, work-order, and exception services own their lifecycle transitions. Statuses such as outbound confirmation/completion, picking progress, load dispatch, and exception resolution are not derived from scan input today.
- PHASE 11.0 therefore treats all matched business entities as read-only references. It records what was scanned and whether it matched session context, but does not call any existing transition service.

## Existing security and transaction conventions

- Read access is restricted through the PHASE 10.5 warehouse/customer scope helpers in `access_policy.py`.
- Outbound mutations require the existing `manage_outbound` permission (`ADMIN`, `MANAGER`, `OUTBOUND`, or `WAREHOUSE`).
- API handlers own commit/rollback. The database dependency does not auto-commit.
- Business timestamps use timezone-aware columns. Operational business dates use the centralized `business_time` utilities and `America/Los_Angeles` by default.

PHASE 11.0 will reuse those conventions. Scan session/event endpoints will not introduce a separate permission system or expose entities outside a caller's existing warehouse/customer scope.

## Existing frontend execution surfaces

- Outbound Dispatch Workbench is the primary order/allocation/picking/BOL execution surface.
- FBA Workbench and Container Tracking expose source inventory and dispatch context.
- Load Management, Work Orders, and Exceptions expose the later execution and coordination stages.
- None of these pages currently owns a continuous keyboard-wedge capture loop or an immutable raw-scan history. PHASE 11.0 adds a separate Scan Workbench and links it through the existing application shell without replacing those workflows.

## Identifier support matrix

The first resolver accepts exact, case-insensitive matches only where the current schema provides a stable operational identifier.

| Scan type | Stable identifier | PHASE 11.0 support | Notes |
| --- | --- | --- | --- |
| Outbound | `OutboundOrder.ob_no` | Yes | Unique and indexed. |
| Picking | `PickingList.picking_no` | Yes | Unique and indexed; scoped through its outbound order. |
| FBA | `FBAShipment.fba_no` | Yes | Unique and indexed; secondary FBA references remain search-only. |
| Location | `WarehouseLocation.location_code` | Yes | Resolved inside the scan session warehouse. |
| Inventory lot | `InventoryLot.lot_no` | Yes | Unique and indexed. |
| Container | `InventoryLot.container_number` | Yes | Represents all matching lots in the session warehouse; it is not treated as a unique inventory-lot primary key. |
| Load | `Load.load_no` | Context validation only | A session can bind to a load; load scanning is deferred until an explicit Phase 11 workflow requires it. |
| Pallet / LPN | None | No | The current schema has quantities but no stable pallet/LPN entity or barcode. |
| SKU | None | No | The current inventory schema has no SKU master or stable SKU barcode. |

Unsupported identifiers are deliberately reported as `NOT_FOUND`; the resolver will not infer them from fuzzy global-search aliases.

## Normalization and duplicate boundary

- Scanner transport whitespace is normalized by trimming leading/trailing whitespace and removing CR/LF characters.
- Punctuation and meaningful character case are preserved in the recorded normalized value.
- Matching is case-insensitive only for identifier columns where that is operationally valid.
- A value already accepted in the same session is recorded as a new `DUPLICATE` event. It does not accumulate quantity or mutate the matched entity.

## Context validation path

- Every session is bound to one warehouse.
- Optional outbound, picking, and load bindings must exist in the same warehouse and be visible under the caller's existing scope.
- A picking binding derives and validates its outbound binding.
- Inventory lots and containers must belong to the bound outbound allocation when an outbound context exists.
- Locations must belong to the session warehouse and, when a picking context exists, must occur on that picking list.
- FBA and picking scans must match the bound outbound when an outbound context exists.
- Cross-warehouse matches return a structured warehouse error only when the caller is authorized to know that entity exists; otherwise the result remains `NOT_FOUND` to prevent scope leakage.

## PHASE 11.0 implementation path

1. Add `ScanSession` and append-only `ScanEvent` tables and a forward Alembic migration.
2. Add a centralized resolver/service for normalization, exact matching, scope/context validation, duplicate detection, counters, and terminal-state handling.
3. Add session lifecycle and scan APIs with explicit transactions and existing RBAC dependencies.
4. Add a keyboard-wedge Scan Workbench that consumes those APIs and keeps the input focused.
5. Verify SQLite unit behavior, PostgreSQL migration/runtime behavior, frontend production build, and a browser-level manual smoke checklist.

## Explicit non-goals

- No inventory quantity mutation.
- No picking, load, work-order, exception, or outbound status mutation.
- No pallet/LPN or SKU data model.
- No camera/mobile scanner integration.
- No offline queue, batch quantity, or scan-driven completion logic.
- No PHASE 11.1 workflow behavior.
