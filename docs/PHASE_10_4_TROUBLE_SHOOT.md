# PHASE 10.4 — Trouble Shoot / Exception Center Foundation

## Delivered scope

- Added `OperationalException` and append-only `OperationalExceptionEvent` persistence.
- Added exception types `INVENTORY`, `PICKING`, `OUTBOUND`, `CONTAINER`, `DOCUMENT`, `APPOINTMENT`, `WAREHOUSE`, `DATA`, and `OTHER`.
- Added severities `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL`; statuses `OPEN`, `INVESTIGATING`, `RESOLVED`, and `CANCELED`.
- Added daily exception numbers in the form `EX-YYYYMMDD-XXXX` with a unique database constraint.
- Added related-object links for Outbound, Load, Container Tracking, Picking List, and BOL. At least one related object is required.
- Added active-exception deduplication for the same exception type and related business object.
- Added assignment, transition, resolution, event-history, and create-work-order APIs.
- Linked exception-created work orders back to the exception. They use type `CHECK` and priority `HIGH`; work-order completion does not resolve an exception automatically.
- Added active exception summaries to Load responses and the Loads page.
- Added Outbound integration: entering `EXCEPTION` creates/deduplicates an Outbound exception; confirming from `EXCEPTION` resolves its active Outbound exceptions.
- Container exceptions remain manual-only in this phase.
- Added the Operations → Trouble Shoot page, dense filters, status tabs, age display, detail drawer, related navigation, actions, linked work orders, and event history.
- Added Operational Exceptions to global search.

## Lifecycle rules

- `OPEN` → `INVESTIGATING`, `RESOLVED`, or `CANCELED`
- `INVESTIGATING` → `RESOLVED` or `CANCELED`
- `RESOLVED` and `CANCELED` are terminal
- Resolution text is required when moving to `RESOLVED`.
- Every create, assignment, status change, resolution, and work-order link writes an immutable event record.

## API surface

- `GET /api/v1/operational-exceptions`
- `POST /api/v1/operational-exceptions`
- `GET /api/v1/operational-exceptions/{id}`
- `PATCH /api/v1/operational-exceptions/{id}`
- `POST /api/v1/operational-exceptions/{id}/assign`
- `POST /api/v1/operational-exceptions/{id}/status`
- `POST /api/v1/operational-exceptions/{id}/resolve`
- `GET /api/v1/operational-exceptions/{id}/events`
- `POST /api/v1/operational-exceptions/{id}/work-orders`

Read endpoints use authenticated access; mutations reuse warehouse write authorization. This matches the current application authorization model; no separate row-scope framework exists yet.

## Database migration

Apply Alembic revision `20260830_0017_operational_exceptions` after the Phase 10.3 head.

## Verification

The focused regression suite covers creation, reference validation, deduplication, lifecycle enforcement, required resolution, immutable history, assignment, work-order linkage, Load summaries, and Outbound integration.

PHASE 10.5 is intentionally outside this delivery.
