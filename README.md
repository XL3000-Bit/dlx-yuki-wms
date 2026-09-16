# DLX Yuki WMS V3

Production-oriented WMS rebuilt in controlled phases. **Current scope: PHASE 1–7** (platform, authentication, master data, Inbound, Inventory, FBA, Outbound, Picking, BOL, and production readiness).

## Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Node.js 20+

## Backend setup (PowerShell)

```powershell
cd C:\Users\XL\dlx-yuki-wms\backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set DATABASE_URL and JWT_SECRET_KEY
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` and `http://localhost:8000/health`. Create the first admin exactly once through `POST /api/v1/users/bootstrap`, then use `/api/v1/auth/login`.

## Tests

From the repository root, with your backend virtual environment activated, install
the test dependencies before running tests. If already in `backend`, skip `cd backend`.
`requirements-test.txt` includes the backend dependencies plus test-only packages
such as `pypdf`; the production installation above remains unchanged.

```powershell
cd backend
python -m pip install -r requirements-test.txt
python -m pytest
```

## Frontend skeleton

```powershell
cd frontend
npm install
npm run dev
```

## PHASE 2: Inbound and Excel Import

After signing in, open `/inbound` for Inbound Management and `/import-history` for import jobs. The workflow supports create/edit, server-side filtering, xlsx export/template, and a controlled five-step import: upload, mapping, validation, confirmation, result.

Supported import formats: standard `.xlsx` files produced by Microsoft Excel or WPS, and UTF-8 `.csv`. Legacy binary `.xls` is intentionally not supported in PHASE 2; save it as `.xlsx` or `.csv` first.

Imports never insert during preview. Confirm revalidates the stored row snapshots and writes all accepted inbound records in one transaction. Duplicate handling supports `SKIP` (default) and `UPDATE`.

West Coast 4.0 (`美西仓 - 4.0`) is detected when the workbook contains sheets `OL`, `DS`, and `出库`. Do not upload the full ~297 MB source file. Follow the operator guide and empty templates:

- [West Coast 4.0 import console](docs/WEST_COAST_4_0_IMPORT_CONSOLE.md)
- Templates: `docs/import-templates/`

Order: master data → 提柜 / Container Tracking → OL → outbound + DS. Close 仓点 / customer gates and reconcile 5–10 containers before bulk load.

## PHASE 3: Inventory

Inventory lots are created only through `POST /api/v1/inbound/{id}/receive-to-inventory` for Put Away or Completed inbound records. Open `/inventory` to search lots, inspect aging/priority and transaction history, or perform controlled Move, Adjustment, Hold and Release operations.

Every quantity-changing operation locks the lot, updates quantities, inserts an inventory transaction with before/after snapshots, and writes an audit log in the same transaction. Inventory is never created manually from the frontend.

## PHASE 4: FBA

Open `/fba` to create an Amazon shipment, resolve its FC address, allocate available inventory, partially or fully release allocations, manage validated status transitions, import allocation plans, and export the current filter to `.xlsx`.

FBA quantities are computed exclusively from `fba_inventory_allocations`; they are never manually stored on the shipment. Allocation and release lock current database rows and atomically update Inventory, transaction history, and audit history. FBA import reuses the common preview → mapping → validation → confirm framework and groups rows with the same FBA number.

## PHASE 6: Picking and BOL

Outbound allocations can generate one or more snapshot-based Picking Lists at `/outbound/picking`; remaining quantities prevent over-planning and picking completion does not alter inventory. `/outbound/bol` lists BOLs generated from outbound allocations, with warehouse ship-from and Amazon FC ship-to data, XLSX export, and a first printable PDF response. `/outbound/picking-history` provides the picking history view.

## PHASE 7: Production Readiness

The browser persists the access/refresh token pair and automatically refreshes an expired access token once before retrying a request. Configure a real PostgreSQL `DATABASE_URL` in `backend/.env`, run `alembic upgrade head`, then create the first administrator once with `POST /api/v1/users/bootstrap`. PostgreSQL backup and restore helpers are provided at `backend/scripts/backup.ps1` and `backend/scripts/restore.ps1`; both require `pg_dump`/`pg_restore` and `DATABASE_URL`.

## PHASE 9.5: Dispatch Intelligence

Container Tracking, FBA Workbench, and the Outbound Workbench expose a live earliest outbound date derived from active outbound allocations. Dispatch priority is separate from inventory-aging priority: overdue/today is CRITICAL, 1–2 days is HIGH, 3–5 days is MEDIUM, and later or unscheduled inventory is NORMAL. Canceled and completed outbound work does not create pending urgency. Container filters and sorting are stored in the URL, and container detail links directly to the selected outbound order.

Detailed calculation, readiness, page behavior, acceptance criteria, and limitations are documented in [Dispatch Priority and Readiness](docs/dispatch-priority.md).

Operational dates use `BUSINESS_TIMEZONE=America/Los_Angeles` by default. Set the same value in `backend/.env` when deploying; naive outbound schedule input is interpreted in this timezone.
