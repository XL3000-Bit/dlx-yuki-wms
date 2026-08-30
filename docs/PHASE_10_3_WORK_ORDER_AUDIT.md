# PHASE 10.3 — Work Order Audit & Event History

## Scope

This phase adds an append-only audit history for work orders, exposes it through a read-only API, and renders it in the Work Order and Load workflows. It builds on the existing `work_order_events` model and migrations rather than introducing a second audit subsystem.

## Migration

No new migration is required. The existing migrations already provide the event table and its structured generic-change fields:

- `20260829_0015_work_order_events.py`
- `20260830_0016_work_order_event_generic_fields.py`

## Event Types

| Event type | Emitted when |
| --- | --- |
| `WORK_ORDER_CREATED` | A work order is created successfully. |
| `WORK_ORDER_UPDATED` | A supported generic field changes. In the current update contract, this is `scheduled_at`. |
| `ASSIGNED` | An unassigned work order gains a user or team assignment. |
| `REASSIGNED` | An existing user/team assignment changes to another assignment. |
| `UNASSIGNED` | The existing user/team assignment is removed. |
| `STATUS_CHANGED` | A valid status transition succeeds. |
| `PRIORITY_CHANGED` | Priority actually changes. |
| `NOTE_UPDATED` | Notes actually change. |

`RELATED_OBJECT_CHANGED` is reserved but is not emitted in this phase because the current Work Order update schema does not permit changing related objects. This avoids recording an event for an unsupported operation.

## Emission Rules

- Events are inserted in the same transaction as the successful work-order mutation.
- Failed validation, invalid transitions, and rejected terminal-state mutations do not create events.
- Repeating the existing value is a no-op and does not create an event.
- Dedicated changes such as assignment, priority, notes, and status do not also emit a duplicate generic update event.
- Event rows are append-only; the application exposes no update or delete operation for them.
- Structured `old_value` and `new_value` fields contain only audit-safe values. Assignment values contain user/team identifiers, not user credentials or other sensitive data.
- The event actor is the authenticated user responsible for the mutation. Historical rows without an actor are presented as `System`.

## Event API

`GET /api/v1/work-orders/{work_order_id}/events`

The endpoint requires normal API authentication and verifies that the work order exists.

Query parameters:

- `order`: `asc` or `desc` (default `desc`)
- `limit`: 1–100 (default 50)
- `offset`: zero-based offset (default 0)

The response contains `data`, `total`, `limit`, and `offset`. Each event includes its identifier, type, timestamp, actor, structured old/new values, message, and compatibility fields used by existing event records. Ordering uses timestamp and event identifier for deterministic results.

## Work Order History UI

The Work Order detail drawer now includes a real History section. Events are fetched only while a work order is selected and are displayed in a compact list with:

- Time
- Actor
- Event
- Details

The view includes loading, error, and empty states. Mutation success invalidates the selected work order's history query so newly appended events appear without a page reload.

## Load Integration

Work Order numbers in the Load detail drawer are clickable. Selecting one opens a work-order detail drawer with overview, relationships, execution data, notes, and History.

The Load response continues to return work-order summaries only. Work-order detail and event history are fetched lazily after a user selects a work order, preventing event-history N+1 requests while loading a Load.

## Verification

Backend coverage includes:

- Event creation shape, actor, timestamp, authentication, and missing-work-order behavior
- Assignment, reassignment, and unassignment classification
- Same-value deduplication
- Priority, notes, scheduled-time, and status changes
- Invalid and terminal-state mutations producing no events
- Ascending/descending ordering, pagination, and parameter validation
- Load integration without embedded event history and lazy event retrieval

Frontend verification uses the TypeScript production build.

## Known Limitations

- Related objects cannot currently be changed through the Work Order update contract, so `RELATED_OBJECT_CHANGED` is not emitted.
- Actor display is based on the stored user relationship; deleted or legacy actors fall back to `System`.
- History is read-only and does not include export, notifications, KPI, accounting, or troubleshooting features.
