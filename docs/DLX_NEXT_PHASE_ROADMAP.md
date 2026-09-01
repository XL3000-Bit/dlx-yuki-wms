# DLX Yuki WMS — Next Phase Roadmap

**Roadmap date:** 2026-08-31
**Baseline:** PHASE 10 frozen RC plus completed PHASE 11.0 and PHASE 11.1 execution foundations

## Release baseline

```text
PHASE 10
FORMAL RELEASE CANDIDATE
FROZEN

PHASE 11.0
Scan Execution Foundation
COMPLETE

PHASE 11.1
Picking Scan Workflow
COMPLETE
```

PHASE 10's PostgreSQL migration blockers are closed. The 0019/0020 enum lifecycle and 0021 schema alignment were verified with Fresh PostgreSQL, `0012 -> head`, `alembic check`, automated tests, and final manual smoke. `20260830_0020` must not be carried forward as an open roadmap blocker.

PHASE 11.0 established `ScanSession`, immutable `ScanEvent`, the scan workbench, RBAC enforcement, PostgreSQL verification, and a 127-test backend baseline. PHASE 11.1 then added transactional PICK execution, idempotency/concurrency guarantees, and a 135-test backend baseline.

## Current P0

| Order | Milestone | Status | Outcome |
| ---: | --- | --- | --- |
| 1 | PHASE 11.1 — Picking Scan Workflow | COMPLETE | Scan-confirmed picking updates outbound and inventory state transactionally |
| 2 | PHASE 11.2 — Staging / Load Verification | NEXT | Verify staged handling units and load membership before dispatch |
| 3 | PHASE 11.3 — Dispatch Readiness Gate | PENDING | Block dispatch until required execution evidence and exception state are valid |
| 4 | POD Closure Workflow | PENDING | Capture proof, resolve delivery exceptions, and close the outbound lifecycle |

The NEXT 10 list retains PHASE 11.1 as a completed baseline. The first development task still open is PHASE 11.2.

## NEXT 10 DEVELOPMENT TASKS

### 1. PHASE 11.1 — Picking Scan Workflow

**Status:** COMPLETE

Delivered transactional PICK behavior, quantity validation, inventory/outbound updates, idempotency, concurrency protection, RBAC, PostgreSQL verification, and regression coverage.

No new PHASE 11.1 feature work is planned. Treat its behavior as the input contract for staging.

### 2. PHASE 11.2 — Staging / Load Verification

**Status:** NEXT
**Priority:** P0

Implement the execution step between picking and dispatch:

- scan or otherwise verify staged handling units
- validate outbound, warehouse, quantity, and load association
- prevent cross-warehouse and cross-outbound contamination
- record immutable execution evidence
- make retries idempotent and concurrent attempts safe
- expose actionable mismatch and incomplete-state errors

Do not weaken existing inventory or outbound invariants to achieve parity with an external UI.

The separate EasyFreight parity-capture artifact currently labeled PHASE 11.2 remains a read-only evidence track. Controlled writes stay blocked until a designated safe test environment and fixture are approved. That artifact is not implementation authorization.

### 3. PHASE 11.3 — Dispatch Readiness Gate

**Status:** PENDING
**Priority:** P0

Create one authoritative readiness decision that checks:

- required quantities picked and staged
- load verification complete
- unresolved blocking exceptions absent
- warehouse and load identities consistent
- required documents and operational approvals present

Dispatch must fail closed with explicit reasons when a required condition is not met. Repeated dispatch requests must not duplicate inventory, notification, history, or external effects.

### 4. POD Closure Workflow

**Status:** PENDING
**Priority:** P0

Complete the outbound lifecycle with:

- POD document capture and versioning
- delivery status and receipt metadata
- missing/invalid POD exception path
- linked work-order support where operational follow-up is required
- immutable closure history and permission enforcement

### 5. SKU Master Foundation

**Status:** PENDING
**Priority:** P1

Introduce canonical SKU identity, customer ownership, units of measure, dimensional data, and lifecycle controls. Avoid duplicating SKU definitions inside receipts, inventory rows, or outbound lines.

### 6. LPN / Pallet Identity

**Status:** PENDING
**Priority:** P1

Add durable handling-unit identity with parent/child relationships, warehouse ownership, content traceability, status, and auditable movement history. Reuse scan sessions and events as the execution surface.

### 7. Cycle Count

**Status:** PENDING
**Priority:** P1

Support count plans, blind counting, discrepancy review, approval, adjustment, and audit history. Preserve separation between observed counts and approved inventory mutations.

### 8. Scan-Driven Inventory Execution

**Status:** PENDING
**Priority:** P1

Extend the established scan foundation to receiving, putaway, movement, cycle count, adjustment, and shipment confirmation. Each mutation must be warehouse-scoped, idempotent, auditable, and transactionally consistent.

### 9. Billable Event and Transactional Outbox

**Status:** PENDING
**Priority:** P1

Derive stable billable events from committed WMS operational events and publish them through a transactional outbox. Include deterministic event identity, versioning, retry state, and reconciliation metadata.

### 10. Accounting Adapter and Reconciliation

**Status:** PENDING
**Priority:** P2

Deliver billable events to the selected accounting or ERP system through an adapter with retry, dead-letter visibility, external identifiers, and reconciliation reporting.

The architecture boundary is:

```text
WMS Operational Event
        ↓
Billable Event
        ↓
Transactional Outbox
        ↓
Accounting Adapter
        ↓
External accounting / ERP
```

Do not implement a general ledger, accounts receivable, accounts payable, tax engine, or financial close inside DLX WMS.

## Delivery dependencies

```text
PHASE 10 frozen RC
        ↓
PHASE 11.0 scan foundation (complete)
        ↓
PHASE 11.1 picking (complete)
        ↓
PHASE 11.2 staging / load verification
        ↓
PHASE 11.3 dispatch readiness
        ↓
POD closure
        ↓
Inventory identity and count expansion
        ↓
Billable events / outbox / accounting adapter
```

## Cross-cutting acceptance gates

Every new execution milestone must preserve:

- warehouse-scoped authorization and data visibility
- immutable and attributable operational history
- idempotency and concurrent-request safety
- PostgreSQL-first migration and lifecycle verification
- fresh-schema and upgrade-path validation
- backend regression coverage and scoped security tests
- frontend build and critical browser workflow smoke
- `git diff --check`
- no Critical or High release issue

## Roadmap constraints

- Do not reopen or silently modify the frozen PHASE 10 RC baseline.
- Do not list scan infrastructure as missing; extend the existing PHASE 11 foundation.
- Do not infer EasyFreight write contracts from read-only observations.
- Do not use production EasyFreight records for parity experiments.
- Do not weaken database constraints to make workflow tests pass.
- Do not rebuild accounting or general-ledger functionality inside the WMS.
