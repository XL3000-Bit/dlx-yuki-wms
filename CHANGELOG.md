# Changelog

## PHASE 10.6 — Operations KPI & Command Dashboard

- Adds Operations Command Center at `/` with scoped warehouse + business-date filters.
- Single aggregation API `GET /api/v1/dashboard/operations` (summary, loads, work orders, exceptions, aging, warehouse breakdown, attention, recent activity).
- Snapshot metrics stay current; period presets apply to created/completed counts only.
- Average exception resolution returns null when there are no resolved samples.
- Dashboard numbers click through to existing Loads / Work Orders / Trouble Shoot URL filters.
- No new chart library and no employee scorecards.

## PHASE 9.5 — FBA / Outbound Dispatch Intelligence

- Derives each source container's earliest outbound date from the minimum `schedule_pickup_at` of active outbound allocations.
- Excludes canceled and completed outbound orders and fully completed allocation quantities from pending dispatch urgency.
- Adds warehouse days, outbound days remaining, dispatch priority, and conservative dispatch readiness to container tracking.
- Adds outbound-date and dispatch-priority filters plus dispatch/aging/date sorting with URL query persistence.
- Adds a container dispatch overview and related outbound task table with links to the selected OB in Outbound Workbench.
- Adds dispatch fields to FBA workbench rows and selected export, including real Excel date values.
- Improves the Outbound Workbench remaining-source table with inbound date, warehouse days, earliest outbound, and dispatch priority; urgent sources sort first.
- Extends outbound import mapping for Outbound Date, Ship Date, Scheduled Outbound, 出库日期, and 最早出库时间. These headers map to the row/order schedule only; container earliest outbound remains calculated.
- Adds reusable backend dispatch rules and frontend priority/date/readiness indicators.
- No migration was required; values are calculated from existing indexed relationships and outbound schedule fields.

Priority thresholds: overdue or today = CRITICAL; 1–2 days = HIGH; 3–5 days = MEDIUM; more than 5 days or unscheduled = NORMAL.
