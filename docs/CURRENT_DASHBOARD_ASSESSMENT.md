# CURRENT_DASHBOARD_ASSESSMENT

Source: `phase-10.3-work-order-audit` after PHASE 10.5.
Date: 2026-08-30.
Updated after PHASE 10.6 implementation.

## Existing widgets (pre-10.6)

There was **no** Operations Dashboard route, page, or widget set.

- App default route was `/inbound`.
- AppLayout menu had no Dashboard item.
- Closest operational surfaces: Outbound Dispatch workbench, FBA workbench, Loads, Work Orders, Trouble Shoot.

## Existing APIs (pre-10.6)

No `/dashboard` or operations summary endpoint.
Counts came from list endpoints:

- Exception list returns `counts` by status (same warehouse filter as the list).
- Load / Work Order lists return `meta.total` after optional filters.
- Outbound workbench has its own listing, not a command summary.

## Existing filters

- Pages use local React state plus some `?selected=` / `?selected_ob=` query params.
- Work Orders and Trouble Shoot had status/severity/warehouse filters in the UI, but they did **not** initialize from `?status=` / `?severity=` before 10.6.
- No shared Dashboard date-range control. Business calendar helpers already exist in `app/utils/business_time.py` (`America/Los_Angeles`).

## Existing counts

Exception tab counts are list-scoped, not a dashboard contract.

## Existing warehouse/date behavior

- Warehouse selectors call `/master-data/warehouses` (PHASE 10.5 scoped).
- Date math uses `get_business_today` / `business_day_range`.

## Reusable frontend components

Reuse AppLayout, Ant Design Card/Statistic/Table/Progress/Tag, DLX orange theme, `usePermissions`, master-data warehouse list, existing list pages for click-through. Do **not** add a chart library.

## Missing operational metrics (filled by 10.6)

Active loads, outbound ready/active, open WO/exceptions, critical exceptions, completed today, aging buckets, warehouse breakdown, attention queue, recent activity, average resolution time.

## Decision

Do not create a second dashboard. Add the first Operations Command Dashboard at `/` (keep `/inbound`). Single aggregation API: `GET /api/v1/dashboard/operations`.
