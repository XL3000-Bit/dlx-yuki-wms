# PHASE 10 Test Report

Run date: 2026-08-30. Overall result: **NOT READY FOR RC**.

## Backend regression

Command: `python -m pytest -ra` with an OS temporary `--basetemp`.

- Total: 119
- Passed: 119
- Failed: 0
- Skipped: 0
- Warnings: 1 (`PytestCacheWarning`, existing `.pytest_cache` permission denied)
- Duration: 14.08 seconds
- Result: PASS

## Security regression

Focused suites: scoped RBAC, Global Search, Documents, Notifications, Dashboard, Work Orders/events, and Operational Exceptions.

- Total/passed: 40/40
- Result: PASS
- Coverage intent: roles, warehouse isolation, list/detail/count/event/search/download/lookup/mutation boundaries.

## Migration and PostgreSQL

- Single Alembic head: PASS (`20260830_0020`).
- Empty PostgreSQL schema upgrade: corrected `0019` PASS; FAIL at `0020`, duplicate `notification_type` creation.
- Isolated PostgreSQL `20260828_0012 -> head`: `0012` PASS; FAIL at `0020`. The development schema was not modified.
- `0019 -> downgrade 0018 -> upgrade 0019`: PASS; downgrade leaves zero dependent tables and zero operational-document enum types.
- Empty PostgreSQL database: NOT RUN; application role lacks `CREATEDB`.
- PostgreSQL status: **NOT VERIFIED**.

## Frontend build

Command: `npm run build`.

- Result: PASS
- Modules transformed: 5,015
- Main application JS: 248.31 kB / 81.96 kB gzip
- Ant Design vendor JS: 1,168.79 kB / 364.42 kB gzip
- Warning: one minified chunk exceeds 500 kB

## Repository and smoke status

- `git diff --check`: exit 0; no whitespace errors. It also reported permission-denied reads for ten user-owned, tracked-but-deleted files under `backend/.pytest-tmp` and CRLF normalization warnings.
- Manual smoke checklist: NOT RUN; blocked by migration provisioning failure.
- No new migration, version change, or git tag was created.

## Acceptance blockers

1. Correct the equivalent PostgreSQL enum lifecycle defect in unreleased migration `0020`, with explicit authorization, then rerun fresh-schema and `0012 -> head` validation.
2. Complete and sign off the manual smoke checklist after migrations pass.
