# PHASE 10.2 — Warehouse Work Order Foundation

## Domain and types

`WorkOrder` is a warehouse execution wrapper, not a replacement for PickingList rows. Supported types are `PICK`, `STAGE`, `LOAD`, `CHECK`, and `GENERAL`. The model links to Warehouse and optionally Load, OutboundOrder, PickingList, and ContainerTracking. Assignment uses existing `User.assigned_to` plus a small `assigned_team` string because no labor/team master exists.

## Status and priority

Statuses: `OPEN`, `ASSIGNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELED`. Valid transitions are enforced server-side: open to assigned/in-progress/canceled, assigned to in-progress/canceled, and in-progress to completed. Completed/canceled work orders are terminal. Priority is `LOW`, `NORMAL`, `HIGH`, or `URGENT`, defaulting to NORMAL.

## Database and numbering

Migration `20260829_0014_work_orders` creates `work_orders` with explicit foreign keys and indexes for number, type, status, warehouse, related objects, priority, assignee and creator. Numbers use the project date-sequence style as `WO-YYYYMMDD-XXXX` with a unique index. No old migration is modified.

## API

`GET /api/v1/work-orders` supports query, status, type, warehouse, priority and assignee filters. Detail, create, patch and status-transition endpoints are available at `/api/v1/work-orders/{id}`. Writes use existing warehouse-write permission; reads use authenticated read access.

## UI

Operations → Work Orders provides a compact Ant Design list, filters, create modal, detail drawer, and state-aware execution buttons. Detail sections cover Overview, Related Objects, Execution, Notes and a truthful History placeholder.

## Load, Outbound and Picking integration

Load detail now exposes Work Orders with number, type, status, priority, assignment and timestamps. Work orders may be load-level, outbound-level, or linked to a PickingList; existing Picking remains the source of item-level execution detail. Related Load/Outbound warehouse mismatches and terminal Load/Outbound references are rejected.

## Global Search

Phase 10.0 search is extended with `WORK_ORDER` and `work_order_no`. Existing ranking and grouped response behavior remain unchanged. Results navigate to `/work-orders?selected=<id>`.

## Validation and tests

The service validates warehouse and related object existence, warehouse consistency, terminal related objects, assignee existence, priorities, duplicate-safe numbering and status transitions. Backend tests cover creation, numbering, relation variants, mismatch/invalid references, assignment, priority, transitions, terminal state, filters, detail, search and authentication; existing Load/Search/Outbound tests remain green.

## Known limitations

No labor payroll, time clock, scheduling engine, automatic task-chain generation, KPI scoring, route planning, GPS, EDI, POD, accounting or carrier portal is included. History is not persisted until a shared audit/history foundation is introduced.
