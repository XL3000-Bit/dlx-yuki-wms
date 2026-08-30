# CURRENT_NOTIFICATION_ASSESSMENT

## Current state

The application has no unified notification model, API, unread state, or header notification UI. Operational attention is currently represented in three separate places:

- `OperationalException` and its event history provide the durable source of truth for exception severity, status, assignment, and resolution.
- `WorkOrder` and its event history provide the durable source of truth for priority, assignment, schedule, and terminal state.
- The Phase 10.6 operations dashboard computes a transient attention queue for critical open exceptions, urgent open work orders, and work orders open longer than 24 hours. It does not persist recipients or read state.

There is no existing email, SMS, push, webhook, Celery, or Redis notification path to preserve or replace.

## Reliable sources for Phase 10.8

- Critical exceptions are reliable when severity is `CRITICAL` and status is `OPEN` or `INVESTIGATING`.
- Urgent work orders are reliable when priority is `URGENT` and status is `OPEN`, `ASSIGNED`, or `IN_PROGRESS`.
- Work-order overdue status is reliable and must reuse the Phase 10.6 predicate: an open work order with non-null `scheduled_at` earlier than the evaluation time.
- Upcoming load appointments are reliable when `appointment_time` is present and the load is `PLANNED` or `READY`. Phase 10.8 will use one centralized two-hour window.
- Exception aging is measurable from `reported_at`, but Phase 10.6 has buckets rather than a notification threshold. It will not be generated until a product threshold is defined.
- POD pending is not reliably inferable: documents can be attached, but the data model does not identify which loads are contractually expected to have POD or a POD due time. It will not be generated.
- Container tracking has lifecycle timestamps and statuses but no explicit alert/exception flag. Container exceptions already surface through `OperationalException`. A separate container alert will not be inferred from ordinary tracking status.

## Targeting and scope

Notifications will be explicit per-user rows. Assignment takes precedence. If there is no assignee, the source creator/reporter is the reliable owner fallback. Warehouse managers/operators are a final fallback, limited to active users whose Phase 10.5 warehouse scope contains the source warehouse. Administrators will not receive a global broadcast.

Every list, count, detail, and mutation will require both `user_id == current_user.id` and current warehouse-scope access. This deliberately revalidates visibility after creation. Viewer users may receive and read notifications; destination-page permissions remain independently enforced.

The current sources do not carry a consistent direct customer id. Phase 10.8 therefore uses warehouse scope for notification visibility and relies on the destination endpoint to enforce any additional customer-level access for the linked entity.

## Persistence and deduplication

Phase 10.8 will add `operational_notifications`, separate type and severity enums, explicit source/reference/deep-link fields, read timestamps, active state, expiry/resolution time, and a stable dedupe key. A unique `(user_id, dedupe_key)` constraint will make generation idempotent. Re-evaluation updates/reactivates the existing condition row; terminal or no-longer-matching conditions deactivate it, preventing unread regeneration while retaining audit-friendly history.

## Generation strategy

- Event-driven service hooks will run inside exception and work-order create/update/assignment/transition transactions.
- A synchronous evaluation service will handle time-based work-order overdue and load appointment conditions when notifications are listed, counted, or explicitly refreshed.
- No scheduler or external infrastructure will be introduced.

## UI integration

The existing `AppLayout` top bar is the single integration point. A bell with unread badge and drawer will provide loading, error, empty, unread/many states, mark-one, mark-all-visible, refresh, and real deep links. Existing exception, work-order, load, and container pages already understand `selected` query parameters, so no duplicate notification page or parallel business UI is required.
