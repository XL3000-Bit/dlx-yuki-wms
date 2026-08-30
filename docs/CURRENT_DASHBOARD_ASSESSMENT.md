# CURRENT_DASHBOARD_ASSESSMENT

Source: `phase-10.3-work-order-audit` after PHASE 10.5.
Date: 2026-08-30.

## Existing widgets

There is **no** Operations Dashboard route, page, or widget set.

- App default route is `/inbound`.
- AppLayout menu has no Dashboard item.
- Closest operational surfaces are Outbound Dispatch workbench, FBA workbench, Loads, Work Orders, Trouble Shoot.

## Existing APIs

No `/dashboard` or operations summary endpoint.
Counts today come from list endpoints:

- Exception list returns `counts` by status (same warehouse filter as the list).
- Load / Work Order lists return `meta.total` after optional filters.
- Outbound workbench has its own listing, not a command summary.

## Existing filters

- Pages use local React state plus some `?selected=` / `?selected_ob=` query params.
- Work Orders and Trouble Shoot have status/severity/warehouse filters in the UI, but they do **not** initialize from `?status=` / `?severity=`.
- No shared Dashboard date-range control. Business calendar helpers already exist in `app/utils/business_time.py` (`America/Los_Angeles`).

## Existing counts

Exception tab counts are the only dedicated count payload. They are list-scoped, not a dashboard contract, and mix snapshot open counts with the current tab filter.

## Existing warehouse/date behavior

- Warehouse selectors call `/master-data/warehouses` (PHASE 10.5 scoped).
- Date math should use `get_business_today` / `business_day_range`, not the browser timezone alone.

## Reusable frontend components

Reuse AppLayout, Ant Design Card/Statistic/Table/Progress/Tag, DLX orange theme, `usePermissions`, master-data warehouse list, existing list pages for click-through. Do **not** add a chart library.

## Missing operational metrics

Active loads, outbound ready/active, open WO/exceptions, critical exceptions, completed today, aging buckets, warehouse breakdown, attention queue, recent activity, average resolution time.

## Decision

Do not create a second dashboard. Add the first Operations Command Dashboard at `/` (keep `/inbound`). Single aggregation API: `GET /api/v1/dashboard/operations`.
