# PHASE 10.8 — Notification & Operational Alert Foundation

## Foundation

`OperationalNotification` is a user-targeted projection of operational state. It does not replace exception or work-order records. Notifications retain their source reference and deep link, while source pages continue to enforce their own permissions.

## Implemented generation

- Critical open/investigating exceptions (`EXCEPTION_CRITICAL`, `CRITICAL`).
- Urgent non-terminal work orders (`WORK_ORDER_URGENT`, `HIGH`).
- Non-terminal work orders whose `scheduled_at` is in the past (`WORK_ORDER_OVERDUE`, `HIGH`), matching the Phase 10.6 rule.
- Planned/ready loads with a reliable appointment within the centralized two-hour window (`LOAD_APPOINTMENT_UPCOMING`, `WARNING`).

Mutation services synchronize condition changes immediately. Time-based conditions are evaluated without a scheduler when notification list, unread count, or refresh endpoints are called. Terminal/resolved conditions deactivate the corresponding notification.

## Targeting, scope, and deduplication

The recipient order is active assignee, then active reporter/creator, then active scoped manager/warehouse operator. Administrators are not broadcast recipients. Warehouse scope is revalidated on list and write operations. One row per user and stable condition is enforced by `(user_id, dedupe_key)`; an assignment change deactivates the prior recipient's active notification.

## API and UI

- `GET /api/v1/notifications`
- `GET /api/v1/notifications/unread-count`
- `POST /api/v1/notifications/{id}/read`
- `POST /api/v1/notifications/mark-all-read`
- `POST /api/v1/notifications/refresh`

The application header provides an unread badge and drawer with severity, title, source reference, timestamp, mark-all-read, refresh, and exact source deep links. Opening a notification marks it read; opening the drawer does not.

## Intentionally skipped

Exception aging has no approved threshold. POD records have no reliable pending/due semantic. Container tracking has lifecycle statuses but no independent alert flag; container-linked exceptions already notify through the exception source. The enum reserves these types, but Phase 10.8 does not fabricate them. Email, SMS, push, webhooks, Celery, Redis, and a notification-event table are out of scope.
