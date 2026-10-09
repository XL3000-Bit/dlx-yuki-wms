# PHASE 11.2 — Current Staging / Load Verification Assessment

> 历史评估：下文 FACTS ABSENT / NOT STARTED 属于早期快照。当前已有暂存及装车核验，已复用于事务内派发阻断；实际结果见 [2026-10-05 派发闭环验收记录](DISPATCH_CLOSURE_ACCEPTANCE_2026-10-05.md)。

**Assessment status:** PHASE 11.2 FACTS ABSENT

**Implementation status:** NOT STARTED

**Repository baseline:** PHASE 11.0 / 11.1 plus PHASE 11.3B

**Alembic head verified:** `20260830_0023`
**PHASE 11.3 status:** NOT COMPLETE

## Scope and evidence

This is a source-only assessment. It does not implement PHASE 11.2, change business code, create a migration, or complete PHASE 11.3.

The conclusions below are based on the current repository, principally:

- `backend/app/models/load.py` — `Load`, `LoadStatus`
- `backend/app/services/load.py` — load membership, mutation, and transition functions
- `backend/app/api/v1/endpoints/loads.py` — current Load API surface
- `backend/app/models/outbound.py` — `OutboundOrder.load_id`
- `backend/app/models/picking.py` — `PickingList`, `PickingListItem`
- `backend/app/models/scan_execution.py` — `ScanSession`, `ScanEvent`, scan enums
- `backend/app/services/scan_execution.py` — `create_scan_session()`, `scan_value()`, `confirm_pick()`
- `backend/app/models/warehouse.py` — `WarehouseArea`, `WarehouseLocation`
- `backend/app/services/dispatch_readiness.py` — `evaluate_outbound_dispatch_readiness()`, `enforce_outbound_dispatch()`
- `backend/alembic/versions/20260830_0022_scan_execution_foundation.py`
- `backend/alembic/versions/20260830_0023_picking_scan_workflow.py`

## 1. Current Load model, states, and member Outbounds

`backend/app/models/load.py` defines the `loads` table through `Load`. Its lifecycle enum is:

```text
PLANNED -> READY -> DISPATCHED -> COMPLETED
    |         |
    +---------+-> CANCELED
```

The exact allowed transitions are enforced by `TRANSITIONS` in `backend/app/services/load.py`:

- `PLANNED` to `READY` or `CANCELED`
- `READY` to `DISPATCHED` or `CANCELED`
- `DISPATCHED` to `COMPLETED`

A Load stores warehouse, carrier, appointment/destination, driver, tractor/trailer/seal, notes, and audit ownership fields. Member Outbounds are not stored in a separate manifest table. Membership is the nullable foreign key `OutboundOrder.load_id` in `backend/app/models/outbound.py`, exposed as `Load.outbounds`.

`_validate_outbounds()` in `backend/app/services/load.py` locks selected Outbounds, requires the same warehouse, rejects terminal Outbounds, and rejects membership in another Load. `create_load()` and `add_outbounds()` set `OutboundOrder.load_id`; `remove_outbound()` clears it.

There is no persisted Load manifest revision, membership snapshot, quantity snapshot, or verification result attached to this relationship.

## 2. PHASE 11.1 picking facts and aggregation

The real PHASE 11.1 persistence model is:

- `picking_lists` via `PickingList`
- `picking_list_items` via `PickingListItem`
- `scan_sessions` via `ScanSession`
- append-only `scan_events` via `ScanEvent`

`PickingListItem` holds planned and picked pallet/carton/weight/CBM quantities plus its allocation, lot, and location references. `confirm_pick()` in `backend/app/services/scan_execution.py` records an idempotent `PICK_CONFIRMED` scan event and updates the applicable picking item quantities inside the locked scan-session transaction.

The current 11.3B dispatch checker does not derive readiness from `ScanEvent` rows. `evaluate_outbound_dispatch_readiness()` in `backend/app/services/dispatch_readiness.py` sums `PickingListItem.picked_pallet_qty` for the Outbound across non-canceled picking lists and compares that total with allocated pallet quantity. Therefore the reusable picking fact is the item-level picked quantity; scan events remain execution/audit evidence.

## 3. Reusable location and scan infrastructure

There is reusable infrastructure, but it is not yet a PHASE 11.2 fact model:

- `WarehouseLocation` provides warehouse-scoped location IDs and codes.
- `ScanOperationType` already declares `STAGE` and `LOAD_VERIFY` in addition to `PICK`.
- `ScanSession` can carry `warehouse_id`, `outbound_id`, `picking_id`, `load_id`, and `current_location_id`.
- `ScanEvent` provides append-only, idempotency-capable scan evidence.

However, `WarehouseLocation` has no staging-location type or staging designation. A generic warehouse location cannot by itself prove that inventory was staged for a specific Outbound or Load.

Likewise, `scan_value()` currently gives non-PICK sessions generic scan resolution and records `GENERIC_SCANNED`. The scan event enum has location/lot/pick events but no first-class stage-confirmed or load-verified event. There is no current service operation that atomically records a staging placement or verifies a Load manifest.

Conclusion: location identity, scan sessions, and append-only scan mechanics can be reused, but `STAGE` and `LOAD_VERIFY` enum values are capabilities/placeholders, not durable staging or load-verification business facts.

## 4. What the current Load service can and cannot do

Current capabilities in `backend/app/services/load.py` and `backend/app/api/v1/endpoints/loads.py`:

- create, read, list, and update a Load;
- attach and detach Outbounds;
- enforce warehouse and existing-membership boundaries;
- aggregate member Outbound allocation totals for the read model;
- perform the generic Load state transitions defined by `TRANSITIONS`.

Current gaps relevant to PHASE 11.2:

- no stage-confirmation mutation or staging history;
- no verification transaction for a pallet, Outbound, or complete Load;
- no expected-versus-verified manifest comparison;
- no wrong-load, missing-item, or duplicate-verification fact;
- no immutable manifest version or fingerprint;
- no invalidation of earlier verification when Load membership or quantities change;
- no readiness calculation based on staging and verification facts;
- no dedicated Load dispatch command that synchronizes member Outbound states.

The existing `POST /loads/{load_id}/status` endpoint invokes the generic `transition_load()` state change. Its ability to set Load status to `DISPATCHED` is not evidence that staging/load verification exists, and it does not make PHASE 11.2 complete.

## 5. Connection to PHASE 11.3B

`evaluate_outbound_dispatch_readiness()` in `backend/app/services/dispatch_readiness.py` returns `NOT_READY` immediately when `OutboundOrder.load_id` is non-null. It emits:

```text
blocker code: LOAD_DISPATCH_REQUIRED
error code:   DISPATCH_THROUGH_LOAD_REQUIRED
```

`enforce_outbound_dispatch()` consequently prevents a member Outbound from being dispatched through the standalone Outbound endpoint. This is the correct handoff boundary: PHASE 11.3B protects against bypass, while PHASE 11.2 must eventually provide trustworthy staging and load-verification facts.

PHASE 11.2 must not remove this block or automatically dispatch a Load/member Outbound. Load dispatch policy and final readiness enforcement remain later PHASE 11.3 work.

## 6. Minimum persistent facts for a first PHASE 11.2 implementation

Repository search across models, services, and migrations establishes:

| Fact | Current state | New table required? | Assessment |
|---|---|---:|---|
| `StageTransaction` | **ABSENT** | **YES** | A durable, auditable staging placement/removal fact cannot be reconstructed safely from generic scan-session state. |
| `LoadVerificationTransaction` | **ABSENT** | **YES** | Verification needs an immutable result tied to a Load, actor, time, expected item/member, and observed identity/quantity. |
| Manifest fingerprint | **ABSENT** | **NO separate table required** | A persisted fingerprint is required to bind a verification result to an exact manifest snapshot, but it can be a required field on the verification transaction/snapshot rather than a third table. |

The fingerprint is necessary because current Load membership is mutable through `OutboundOrder.load_id`, and picked/allocated quantities can also change. Without a snapshot identity, a previously successful verification could be incorrectly reused after the Load contents change.

The exact columns, constraints, invalidation rules, and fingerprint algorithm are implementation-design work and are intentionally not specified by this assessment. The minimum conclusion is that two new durable transaction tables and persisted manifest binding are required; extending generic scan events alone is insufficient.

## 7. Explicit non-goals

PHASE 11.2 must not, by itself:

- automatically release or dispatch a Load or member Outbound;
- weaken the PHASE 11.3B standalone dispatch block;
- implement PHASE 11.3C or mark PHASE 11.3 complete;
- change POD or delivery-receipt semantics;
- decrement inventory or change allocation/release/completion semantics;
- introduce electronic signatures;
- infer verification solely from `ScanSession`, generic `ScanEvent`, or Load status;
- modify existing migrations.

## Decision

```text
PHASE 11.2 FACTS:              ABSENT
PHASE 11.2 IMPLEMENTATION:     NOT STARTED
NEW MIGRATION REQUIRED:        YES
CURRENT ALEMBIC HEAD:          20260830_0023
EXPECTED IMPLEMENTATION HEAD:  20260830_0024
PHASE 11.3:                    NOT COMPLETE
```

PHASE 11.2 requires a new migration because its minimum durable facts do not exist in the current schema. When implementation is explicitly authorized, Alembic head should advance from `20260830_0023` to `20260830_0024`. This assessment does not create that migration or authorize implementation.
