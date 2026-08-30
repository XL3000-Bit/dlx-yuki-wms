# Phase 10.6 — Operations KPI & Command Dashboard

## Delivered

- Operations Command Dashboard at `/dashboard`, now the authenticated root landing page.
- Warehouse selector and Today, Yesterday, trailing 7 days, month-to-date, and custom date controls.
- KPI cards, load flow, work-order execution funnel, exception control, aging buckets, exception types, attention queue, recent activity, and multi-warehouse breakdown.
- Click-through navigation that preserves relevant warehouse/status/severity query filters.
- One aggregate dashboard API at `GET /api/v1/dashboard/operations`.
- Centralized backend metric definitions and SQL aggregation.
- Warehouse/customer scope enforcement where the underlying entity supplies an authoritative scope key.

No database migration is required for Phase 10.6. The feature reads the Phase 10.2–10.5 data model and event history without adding schema.

Detailed definitions, date semantics, scope behavior, performance decisions, and limitations are recorded in [CURRENT_DASHBOARD_ASSESSMENT.md](./CURRENT_DASHBOARD_ASSESSMENT.md).
