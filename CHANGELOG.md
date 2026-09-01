# Changelog

## Admin data upload (2026-09-01)

- Adds `/admin/data-upload` for `ADMIN` accounts only. Other roles do not see the menu item and are redirected.
- Uploads the four West Coast 4.0 converter files in order: tracking, OL, DS, outbound.
- OL / DS / outbound reuse preview → async validate → Confirm (`SKIP`). Outbound stays locked until OL + DS are confirmed and the inventory checkbox is ticked.
- Container tracking import accepts converter headers (`container_number`, `mbl_number`, `pod_eta`, …) as well as shipmentexport.csv headers.

## West Coast 4.0 converter program (2026-09-01)

- Adds offline program `tools/west_coast_import/convert_west_coast.py` and double-click launcher `CONVERT_WEST_COAST.bat`.
- Inspects the source workbook and exports pilot or named-container CSVs plus `reconcile.json`.
- Does not write to PostgreSQL or call the WMS API. Live system remains `START_DLX_WMS.bat`.
- Guide: `docs/WEST_COAST_IMPORT_TOOL.md`.

## West Coast 4.0 import console (2026-09-01)

- Adds operator guide `docs/WEST_COAST_4_0_IMPORT_CONSOLE.md` for the 297 MB 美西仓 4.0 workbook.
- Documents the required import order: master data → 提柜 / Container Tracking → OL inbound → outbound + DS.
- Records gates: 141 仓点 values, customer matching, one duplicate container, outbound linkage keys.
- Adds empty UTF-8 templates under `docs/import-templates/` that match `WEST_COAST_4_0_*` profile headers.
- Does not change import runtime, preview/confirm behavior, or write production data.

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
