# CURRENT_DASHBOARD_ASSESSMENT

Before Phase 10.6, the application had strong operational list/detail surfaces for loads, outbound dispatch, work orders, and exceptions, but no command-level landing page. The root route opened outbound dispatch, managers had to visit several pages to assemble a warehouse picture, metric definitions were implicit in list filters, and there was no single scoped API for KPI delivery.

Phase 10.6 adds an Operations Command Dashboard as the authenticated landing page. It uses one aggregate API request, existing warehouse/customer access policy, business-day boundaries, and database-side grouped counts. It intentionally reports team and process health only; it introduces no employee ranking or individual productivity metric.

## Metric definitions

All timestamps are interpreted in the configured business timezone. Date ranges are inclusive in the UI and converted to a half-open interval `[period_start, period_end_exclusive)` in the API.

Snapshot metrics ignore the selected date range and describe the current operational state:

- Active loads: current status is `PLANNED`, `READY`, or `DISPATCHED`.
- Outbound ready: current status is `CONFIRMED` or `DISPATCHED`.
- Outbound active: current status is `NEW`, `HOLD`, `IN_PROGRESS`, `CONFIRMED`, `DISPATCHED`, or `EXCEPTION`.
- Open work orders: current status is `OPEN`, `ASSIGNED`, or `IN_PROGRESS`.
- Open exceptions: current status is `OPEN` or `INVESTIGATING`.
- Critical exceptions: open exceptions whose severity is `CRITICAL`.
- Overdue work orders: open work orders with a non-null `scheduled_at` earlier than the snapshot time.
- Work-order aging starts at `created_at`; exception aging starts at `reported_at`.

Period metrics apply the selected half-open interval:

- Loads created: `Load.created_at` falls in the interval. Status grouping is their current status, not a historical transition count.
- Completed work orders: `WorkOrder.completed_at` falls in the interval.
- Resolved exceptions and average resolution hours: `resolved_at` falls in the interval; duration is `resolved_at - reported_at`.
- Average outbounds per created load: outbounds currently linked to loads created in the interval divided by those loads.

The execution funnel is a current-state distribution (`OPEN → ASSIGNED → IN_PROGRESS → COMPLETED`), not a cohort conversion funnel.

## Scope and query behavior

Warehouse scope is applied to every load, work-order, exception, warehouse-breakdown, attention, and recent-activity query. Customer scope is additionally applied to outbound-derived metrics because outbound orders carry a direct customer relationship. Work orders and exceptions currently carry warehouse scope but no authoritative direct customer key, so customer filtering cannot be safely inferred for generic records.

The endpoint is `GET /api/v1/dashboard/operations` with optional `date_from`, `date_to`, and `warehouse_id`. The default is the current business day, the maximum range is 367 days, and inaccessible explicit warehouses are rejected. The frontend performs one dashboard data request and a separate scoped warehouse-selector request.

## Performance notes

Counts, grouped distributions, aging buckets, and resolution averages are computed in SQL. Warehouse fact counts are pre-aggregated before joining to warehouse masters, preventing a work-order × exception multiplication. Recent activity queries read ten rows from each event source and merge the newest fifteen. The attention queue is capped at twelve items.

## Known limitations

- Load history has no authoritative status-transition timestamps, so period load metrics use creation time plus current status.
- Generic work orders and exceptions cannot always inherit customer scope without a direct customer key.
- The command dashboard uses lightweight Ant Design primitives and no chart library; distributions are tables, tags, progress bars, and metric rows.
- Aging reflects elapsed clock time from creation/reporting, not business hours or SLA calendars.
