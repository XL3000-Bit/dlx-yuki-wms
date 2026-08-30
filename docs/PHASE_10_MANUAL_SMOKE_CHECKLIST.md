# PHASE 10 Manual Smoke Checklist

Run date: 2026-08-30. Build: `06a7fae`. Database: local PostgreSQL `dlx_yuki_wms`, migrated to `20260830_0021`. Status: **PASS FOR RC**.

## Browser smoke evidence

- [x] Dashboard rendered its operational summaries, filters, empty states, and Refresh action.
- [x] Global Search found exact outbound `RTPL260829001`; its result opened `/outbound/dispatch?selected_ob=3`.
- [x] Outbound Dispatch restored the selected outbound after refresh and rendered orders, allocation/picking/BOL, remaining source, Reset Window, and right-panel controls.
- [x] Loads rendered its filters, Refresh and Create Load controls, and a safe empty state.
- [x] Work Order `WO-20260830-0001` rendered as COMPLETED with its full OPEN -> ASSIGNED -> IN_PROGRESS -> COMPLETED history.
- [x] Trouble Shoot rendered its filters and empty state, then opened the Create Exception workflow.
- [x] Submitting an exception without an operational reference was rejected without creating a record.
- [x] Exception `EX-20260830-0001` was created against outbound 3. PostgreSQL supplied non-null `created_at`/`updated_at`, and the UI displayed the creation time.
- [x] The exception advanced OPEN -> INVESTIGATING -> RESOLVED and preserved EXCEPTION_CREATED, status-change, and resolution history.
- [x] The exception's outbound deep link targeted `/outbound/dispatch?selected_ob=3`.
- [x] Notifications opened, refreshed, and displayed a safe empty state with Mark All Read disabled.
- [x] No application runtime exception appeared in the browser log.

## Automated acceptance used for non-destructive coverage

- [x] Admin/Manager/Operator/Viewer authorization and cross-warehouse isolation are covered by the full backend suite.
- [x] Load creation, duplicate relation conflicts, lifecycle validation, document upload/version/archive/download, notification dedupe/read handling, and safe API failures are covered by automated tests.
- [x] PostgreSQL fresh-schema, `0012 -> head`, downgrade/re-upgrade, and `alembic check` smoke passed.
- [x] Full backend regression passed after the PostgreSQL smoke.
- [x] Frontend TypeScript compilation and production build passed.

## Deliberate manual-test limits

Only the existing administrator session was available, so the role matrix was not re-created manually. No disposable document fixture or Load fixture was created in the browser. These paths are accepted through automated coverage; no user, permission, or production-like document data was modified.

The browser emitted only the known Ant Design React-version and static-message-context warnings. They did not prevent any tested flow.

## Completion

- [x] Smoke deviations and limits recorded.
- [x] Automated regression rerun after stabilization.
- [x] Phase 10.9 meets the technical RC gate; release-owner promotion remains an operational decision.
