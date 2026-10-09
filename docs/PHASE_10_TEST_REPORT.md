# PHASE 10 Test Report

Run date: 2026-08-30. Overall result: **FORMAL RELEASE CANDIDATE**.

## Backend regression

- `python -m compileall -q app tests alembic`: PASS.
- Focused Operational Exception and Notification suites: **8 passed**, 0 failed, 1 cache-permission warning.
- Full `pytest -ra`: **119 passed**, 0 failed, 0 skipped, 1 cache-permission warning in 15.62 seconds.

The warning is `PytestCacheWarning` for an existing Windows `.pytest_cache` permission condition. It does not affect test execution or application behavior.

## Migration and PostgreSQL

- Single Alembic head: PASS (`20260830_0021`).
- Empty isolated PostgreSQL schema upgrade to head: PASS.
- Empty isolated schema `alembic check`: PASS, no new operations.
- Isolated PostgreSQL `20260828_0012 -> head`: PASS.
- `0021 -> downgrade 0020 -> upgrade 0021`: PASS.
- Existing local PostgreSQL schema repaired from a false `0020` stamp and upgraded through the standard chain: PASS.
- Local `alembic current`: `20260830_0021 (head)`.
- Local `alembic check`: PASS, no drift.
- Operational Exception insertion through the application service: PASS, including non-null timestamps and creation event.

## Frontend

Command: `npm run build` (`tsc -b && vite build`).

- TypeScript: PASS.
- Production build: PASS.
- Modules transformed: 5,015.
- Build duration: 6.34 seconds.
- Known warning: Ant Design vendor chunk is 1,168.79 kB (364.42 kB gzip), above Vite's 500 kB advisory threshold.
- There is no frontend lint or unit-test script in `package.json`.

## Manual smoke

Dashboard, Global Search/deep link, Outbound Dispatch query-state restoration, Loads empty state, completed Work Order history, Trouble Shoot exception validation/create/investigate/resolve/history, and Notifications empty/refresh behavior passed in the browser.

The new exception `EX-20260830-0001` demonstrated that the PostgreSQL timestamp blocker is fixed in the actual UI/service path. Non-destructive role, Load lifecycle, document lifecycle, and notification mutation cases remain covered by automated tests rather than new manual fixtures.

## RC decision

No Critical or High stabilization blocker remains. PostgreSQL migrations, drift detection, backend regression, frontend compilation/build, and the documented manual smoke all pass. Phase 10 meets the technical RC gate.
