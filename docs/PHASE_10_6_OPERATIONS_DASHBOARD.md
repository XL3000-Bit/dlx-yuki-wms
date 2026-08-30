# PHASE 10.6 Operations KPI & Command Dashboard

Branch: `phase-10.3-work-order-audit`.
Inspection first: `docs/CURRENT_DASHBOARD_ASSESSMENT.md`.
This phase does not start PHASE 10.7.

## Dashboard purpose

Operations Command Center at `/`. Answers five questions from real operational tables:

1. How much work is on the floor today?
2. How many tasks are unfinished?
3. How many exceptions are open?
4. What is aging?
5. Where are Load / Outbound / Work Order executions?

Not a scorecard, not Accounting, not BI.

## Metric definitions

Centralized in `operations_dashboard` response `definitions`:

| KPI | Definition | Kind |
| --- | --- | --- |
| Active Load | status in PLANNED / READY / DISPATCHED | snapshot |
| Outbound Ready | CONFIRMED / IN_PROGRESS | snapshot |
| Outbound Active | NEW / HOLD / IN_PROGRESS / CONFIRMED / DISPATCHED / EXCEPTION | snapshot |
| Open Work Order | OPEN / ASSIGNED / IN_PROGRESS | snapshot |
| Open Exception | OPEN / INVESTIGATING | snapshot |
| Critical Exception | open + severity CRITICAL | snapshot |
| Completed Today | `work_orders.completed_at` inside America/Los_Angeles business day | period |
| Loads Created | `loads.created_at` in selected period | period |
| Loads Completed | COMPLETED and `updated_at` in period (no dedicated completed_at) | period |
| Avg OB per active load | outbound rows on active loads / active load count; null if no active loads | snapshot |
| Avg resolution | mean(`resolved_at - reported_at`) for RESOLVED with both timestamps; **null if sample is 0** | period-independent sample |
| Overdue WO | open WO with `scheduled_at` present and `< now`; no scheduled_at is not overdue | snapshot |

## Snapshot vs period metrics

Date presets apply to created / completed / resolved-period style measures only.
Open / active / aging / attention / warehouse breakdown are **current snapshots** and are not wiped when the user picks Yesterday.
Each summary card includes `kind`: `snapshot` or `period`.

## Scope behavior

Reuses PHASE 10.5 `get_access_scope` / `apply_warehouse_scope`.

- All counts, aging, attention, recent events, and breakdown honor warehouse scope.
- Optional `warehouse_id` query is ignored (forced empty) when the warehouse is not visible.
- SELECTED users never see Warehouse B facts on a Warehouse A login.
- Customer scope is not enforceable on Load / Work Order / Exception (no customer FK).

## Date semantics

Presets: `today` (default), `yesterday`, `last_7_days`, `this_month`, `custom` (`date_from` + `date_to`).
Ranges come from `business_day_range` in `America/Los_Angeles`.

## Aggregation API

`GET /api/v1/dashboard/operations`

Query: `warehouse_id`, `preset`, `date_from`, `date_to`.
Auth: any logged-in user (VIEWER read allowed).

Payload: `filters`, `definitions`, `summary`, `loads`, `work_orders`, `exceptions`, `warehouse_breakdown`, `attention`, `recent_activity`.

## Load metrics

Status histogram, active count, created in period, completed in period, average outbounds per active load.
No freight cost.

## Work Order metrics

Status histogram, open priority breakdown, completed today / period, overdue, aging, funnel OPEN → ASSIGNED → IN_PROGRESS → COMPLETED.
Age starts at `created_at` (documented; `started_at` is not used).

## Exception metrics

Status histogram, open severity, open types sorted by count, average resolution seconds or null, aging.

## Aging

Exceptions (OPEN / INVESTIGATING) from `reported_at`:
`< 4h`, `4–12h`, `12–24h`, `1–3d`, `> 3d`.

Work Orders (open set) from `created_at`:
`< 4h`, `4–12h`, `12–24h`, `> 24h`.

Buckets computed in Python from timestamps only (SQLite-safe).

## Warehouse Breakdown

Shown when the caller can see more than one warehouse or has ALL warehouse scope.
Hidden for a single SELECTED warehouse.
Columns: warehouse, active loads, open WOs, open exceptions, critical exceptions.

## Attention Queue

Up to 20 items ranked by severity/priority + age:
CRITICAL exceptions, URGENT work orders, long-aging exceptions/WOs.
Each row links to the existing detail page (`?selected=`).

## Recent Activity

Last 20 Work Order events + last 20 Exception events, merged and trimmed to 15.
Fields: time, type, reference, actor id, summary, target route.
Scoped through parent warehouse.

## UI

`frontend/src/pages/DashboardPage.tsx` at `/`.
Top filters: warehouse (scoped master list) + period preset + custom range.
Six summary cards (click-through), WO funnel, exception aging, type list, optional warehouse table, attention, recent activity.
Ant Design only. No new chart library.

Click-through:

- Open Exceptions → `/trouble-shoot?status=OPEN`
- Critical → `/trouble-shoot?severity=CRITICAL`
- Open Work Orders → `/work-orders?status=OPEN`
- Completed Today → `/work-orders?status=COMPLETED`
- Active Loads → `/loads`
- Outbound Ready → `/outbound/dispatch`

List pages initialize those query params.

## Performance

Status counts are `GROUP BY` aggregates.
Aging/attention load open-row timestamps only, not full graphs.
Events capped at 20 per source.
No new migration. Existing status / warehouse_id / created_at indexes used.

## Tests

`backend/tests/test_operations_dashboard.py`:
admin snapshot vs period, scoped warehouse A vs B, completed today, resolution average vs null, aging, attention, recent activity, viewer 200, search regression.

## Known limitations

- Load completed-in-period uses `updated_at` because loads have no `completed_at`.
- Open Work Orders card links to `status=OPEN` only (not ASSIGNED + IN_PROGRESS).
- Average resolution includes all resolved rows in scope, not the selected period.
- Attention ranking is heuristic, not an SLA engine.
- No employee scores, notifications, Accounting, or predictions.
