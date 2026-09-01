# PHASE 11.3 Current Dispatch Readiness Assessment

Assessment date: 2026-08-31

## Scope and baseline

- `HEAD` is `59d6f5b` on `feature/phase-11-2-staging-load-verification`.
- PHASE 11.3A Outbound Dispatch Hardening exists in the current working tree and is retained.
- Full PHASE 11.3 is **NOT COMPLETE**.
- `HEAD` contains the PHASE 11.0/11.1 scan and picking migrations `20260830_0022` and `20260830_0023`.
- PHASE 11.2 Staging / Load Verification facts are not present in `HEAD` or in the inspected models, services, or migrations.
- This assessment is read-only with respect to application code. It does not define or implement new dispatch, load, scan, staging, or migration behavior.

## 1. Current 11.3A readiness checker

Source: `backend/app/services/dispatch_readiness.py`, function `get_dispatch_readiness`.

The checker currently evaluates these facts:

1. `OutboundOrder.status == OBStatus.CONFIRMED`.
2. At least one `OutboundInventoryAllocation` row has `allocated_pallet_qty > 0`; the checker also sums those positive allocated pallet quantities.
3. The sum of `PickingListItem.picked_pallet_qty` for the Outbound is greater than or equal to the allocated pallet sum. Picking lists with `PickingStatus.CANCELED` are excluded.
4. At least one `BOL` for the Outbound has status `GENERATED`, `PRINTED`, or `COMPLETED`, and a non-empty trimmed `BOL.bol_no`.
5. `OutboundOrder.carrier_id` is not null.
6. No `OperationalException` linked by `outbound_id` has status `OPEN` or `INVESTIGATING`.

The result is `READY` only when all six checks pass; otherwise it is `BLOCKED` with `blocking_reasons`. The checker does not inspect `load_id`, `schedule_pickup_at`, POD, `ScanSession`, `ScanEvent`, staging, or load verification.

Source: `backend/app/services/dispatch_readiness.py`, function `require_dispatch_ready`. A blocked result raises HTTP 409 and includes the readiness details and blocking reasons.

## 2. Outbound dispatch transaction boundary

Endpoint source: `backend/app/api/v1/endpoints/outbound.py`, function `dispatch`.

Service source: `backend/app/services/outbound.py`, functions `get_ob` and `change`.

The endpoint first calls scoped `get_ob(..., user=user)` to enforce visibility, then calls `change(..., target=DISPATCHED)`. Inside `change` the order is:

1. `get_ob(db, ob_id, lock=True)` issues the Outbound row query with `FOR UPDATE`.
2. For a `DISPATCHED` target, `require_dispatch_ready(db, outbound)` runs after the Outbound row lock is acquired.
3. The transition is validated and the Outbound status/timestamps are changed.
4. The service commits the transaction.

Therefore the Outbound row is locked before readiness checking and remains in the same service transaction through the state change and commit. The readiness queries do not explicitly lock the related allocation, picking, BOL, or exception rows. That remaining concurrency-policy question belongs to a later hardening slice; it is not changed by this assessment.

## 3. Load dispatch behavior

Endpoint source: `backend/app/api/v1/endpoints/loads.py`, the `POST /{load_id}/status` handler.

Service source: `backend/app/services/load.py`, function `transition_load`.

There is no dedicated `POST /loads/{id}/dispatch` endpoint. A Load can be moved to `DISPATCHED` through the generic status-transition endpoint when the transition table allows it. `transition_load` changes the Load status and synchronizes Load notifications; it does not iterate over or change the status of member Outbounds.

## 4. Load-bound Outbound bypass

Source: `backend/app/services/dispatch_readiness.py`, function `get_dispatch_readiness`; `backend/app/services/outbound.py`, function `change`.

`OutboundOrder.load_id` is not part of the readiness calculation. Consequently, an Outbound with a non-null `load_id` can currently be dispatched individually when the existing Outbound readiness checks pass. No Load-level gate is consulted.

## 5. PHASE 11.1 picking facts used by 11.3A

Model sources:

- `backend/app/models/scan_execution.py`: `ScanSession` uses table `scan_sessions`; `ScanEvent` uses table `scan_events`.
- `backend/app/models/picking.py`: `PickingList` uses table `picking_lists`; `PickingListItem` uses table `picking_list_items` and stores `picked_pallet_qty`.

Write-path source: `backend/app/services/scan_execution.py`, function `confirm_pick`. A confirmed pick updates the locked `PickingListItem` quantity and creates a `ScanEvent` with event type `PICK_CONFIRMED` through `_new_scan_event`.

Migration source: `backend/alembic/versions/20260830_0023_picking_scan_workflow.py`, revision `20260830_0023`. It adds picking workflow columns and the `PICK_CONFIRMED` scan-event fact.

The 11.3A checker does not read `ScanEvent` transactions. It reads only the materialized picking aggregate: the sum of `PickingListItem.picked_pallet_qty` across non-canceled picking lists.

## 6. PHASE 11.2 fact availability

Search scope: `backend/app/models`, `backend/app/services`, and `backend/alembic/versions`.

- `StageTransaction`: **ABSENT**.
- `LoadVerificationTransaction`: **ABSENT**.
- Manifest fingerprint fact/field/service: **ABSENT**.

Existing scan operation enum names do not constitute PHASE 11.2 transaction facts. No new table or replacement design is proposed here.

## 7. Viewer authorization and status codes

Authorization source: `backend/app/api/deps.py`, function `require_outbound_write`.

Endpoint source: `backend/app/api/v1/endpoints/outbound.py`, functions `dispatch_readiness` and `dispatch`.

- `GET /api/v1/outbounds/{id}/dispatch-readiness` uses `CurrentUser`, not `require_outbound_write`. A Viewer who can see the Outbound receives HTTP 200 and the readiness result. If warehouse/customer scope hides the Outbound, scoped `get_ob` returns HTTP 404.
- `POST /api/v1/outbounds/{id}/dispatch` uses the `Writer` dependency backed by `require_outbound_write`. `VIEWER` is not in its allowed roles, so a Viewer receives HTTP 403 before dispatch logic runs.

## 8. Batch dispatch partial-success semantics

Endpoint source: `backend/app/api/v1/endpoints/outbound.py`, function `workbench_batch`.

The batch handler processes each Outbound separately through the same `change` service used by single dispatch. Each successful `change` commits its Outbound. On an item failure, the handler rolls back that failed item, extracts readiness reasons when present, records the failure, and continues. It returns per-item results plus success and failure counts.

The current contract therefore permits partial batch success: successful Outbounds remain dispatched, while failed Outbounds remain unchanged and carry a failure reason.

## 9. BOL evidence actually checked

Source: `backend/app/services/dispatch_readiness.py`, function `get_dispatch_readiness`.

The checker queries the `bols` table only. It requires an accepted BOL status and a non-empty trimmed `BOL.bol_no`.

Although `OperationalDocument` and `DocumentStatus.AVAILABLE` exist in `backend/app/models/operational_document.py`, the readiness checker does not query `OperationalDocument` and does not require an AVAILABLE BOL document artifact.

## 10. Alembic head

Command executed from `backend`:

```text
.\.venv\Scripts\python.exe -m alembic heads
```

Result:

```text
20260830_0023 (head)
```

There is no `0024` migration in the assessed baseline.

## Assessment conclusion

**A. 11.2 facts ABSENT.**

The next permitted slice can only be **11.3B** covering Viewer/readiness policy, the Load-bound individual-dispatch bypass, explicit policy decisions, and transaction-locking hardening. STALE or manifest-fingerprint behavior cannot be implemented from facts that do not exist. No Load readiness, scan/load service change, or migration was implemented by this assessment.
