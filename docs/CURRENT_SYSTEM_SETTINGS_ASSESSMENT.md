# PHASE 12.0 — System Settings & Master Data Assessment

Date: 2026-09-01  
Scope: read-only assessment. No business-code implementation in this phase.  
Repo inspected: `XL3000-Bit/dlx-yuki-wms` on `main`, plus known local worktree state on `C:\Users\XL\dlx-yuki-wms`.

---

## 0. Phase gate (this document only)

| Question | Answer |
|---|---|
| Only assessment document created? | **Yes** — `docs/CURRENT_SYSTEM_SETTINGS_ASSESSMENT.md` |
| Business code modified in this phase? | **No** |
| Alembic migration created? | **No** |
| Database modified? | **No** |
| Dependencies installed? | **No** |
| Existing worktree formatted/restored/cleaned? | **No** |

This file is the only intended PHASE 12.0 deliverable. Local operators must not treat later UI experiments (Company mega menu, user admin, company profile runtime table) as a completed Phase 12 design. Those experiments exist on `main` / local branches and must be reconciled in 12.1, not expanded blindly.

---

## 1. Current Alembic head

Linear chain on disk under `backend/alembic/versions/`:

```
20260828_0001_phase1_core
  -> 0002 inbound/import
  -> 0003 inventory
  -> 0004 fba
  -> 0005 outbound
  -> 0006 picking/bol
  -> e852423c687a  (phase 7 schema alignment; revises 0006)
  -> 0008 real data import
  -> 0009 long references
  -> 0010 outbound long PO
  -> 0011 container tracking
  -> 0012 container tracking indexes
  -> 0013 load management
  -> 0014 work orders
  -> 0015 work order events
  -> 0016 work order event generic fields
  -> 0017 operational exceptions
  -> 0018 scoped RBAC
  -> 0019 operational documents
  -> 20260830_0020 operational notifications
```

**Declared head in source: `20260830_0020`.**

Notes:
- There is no Alembic revision for `company_profiles`. The experimental Company Profile endpoint creates that table at runtime with `checkfirst=True`. That is schema drift and must be replaced by a real migration in 12.1 if the table is kept.
- There is no `company_id` tenant column anywhere in the core chain. The product is **single-company / multi-warehouse**, not multi-tenant SaaS.
- Confirm live DB with `alembic current` on the server laptop before 12.1. If a local merge branch skipped revisions, stop and repair before any new migration.

---

## 2. Git status and uncommitted work (known)

This assessment cannot run `git status` on `C:\Users\XL\dlx-yuki-wms`. From the live session:

- Local branch observed: `feature/phase-11-2-staging-load-verification`
- That branch was **ahead of its remote by 8 commits** and had an **unfinished merge** (`All conflicts fixed but you are still merging`).
- Unstaged after Codex work included `frontend/src/pages/OutboundDispatchWorkbenchPage.tsx`.
- Files previously involved in the merge index: `CHANGELOG.md`, `backend/app/services/container_tracking.py`, `frontend/src/App.tsx`, `AppLayout.tsx`, `main.tsx`, `styles.css`, `AdminDataUploadPage.tsx`, Dispatch command-bar files.

**12.1 must not start until that merge is concluded or aborted on a clean copy.** Recommended: finish the merge commit on the feature branch, or copy the assessment file onto a clean `main` checkout.

Operator should run locally (not done here):

```powershell
cd C:\Users\XL\dlx-yuki-wms
git status --short
git diff --check
alembic -c backend/alembic.ini current
```

---

## 3. What already exists

### 3.1 Backend models (reuse first)

| Model | Table | Soft-delete / active | Isolation keys |
|---|---|---|---|
| User | `users` | `is_active` | `warehouse_scope_mode`, `customer_scope_mode`, M2M scope tables |
| UserRole | enum | n/a | ADMIN, MANAGER, INBOUND, OUTBOUND, WAREHOUSE, VIEWER |
| Customer | `customers` | `is_active` | none (global, filtered by user customer scope) |
| Warehouse | `warehouses` | `is_active` | warehouse is the isolation unit |
| WarehouseArea | `warehouse_areas` | `is_active` | `warehouse_id` |
| WarehouseLocation | `warehouse_locations` | `is_active` | `warehouse_id`, `area_id` |
| Carrier | `carriers` | `is_active` | global |
| AmazonFCAddress | `amazon_fc_addresses` | `is_active` | global by `fc_code` |
| AuditLog | `audit_logs` | append-only | `user_id`, `entity_type`, `entity_id`, before/after JSON |
| OperationalException | `operational_exceptions` | status machine | `warehouse_id` |
| OperationalDocument | `operational_documents` | document status | linked to OB / inbound / etc. |
| CompanyProfile | `company_profiles` (runtime) | none | singleton row — **not in Alembic** |

Inbound, inventory lots, FBA, outbound, picking, BOL, container tracking, loads, work orders all already FK to `warehouses`, `customers`, and/or `carriers` / FC codes. Do not clone those entities.

### 3.2 Backend APIs already usable

- `GET/POST /api/v1/users`, `PATCH /api/v1/users/{id}`, `PATCH /api/v1/users/{id}/scope`, `GET /users/me`, bootstrap
- `GET/POST /api/v1/master-data/customers|warehouses|warehouse-areas|warehouse-locations|carriers|amazon-fc-addresses`
- Master POST is `require_admin`. GET is scoped via `warehouse_clause` / `customer_clause`.
- `GET/PUT /api/v1/company-profile` (experimental; PUT admin-only; table auto-create)
- Audit rows are written from inbound/inventory/outbound services (`AuditLog`), not from a generic settings service.
- No list/filter API for `audit_logs` was found as a first-class settings page.

### 3.3 Frontend today

- Shell: `frontend/src/layouts/AppLayout.tsx` — navy sider + top search + notifications + gear `CompanyMenu`.
- Routes in `App.tsx`: dashboard, inbound, container-tracking, inventory, FBA, outbound/*, loads, work-orders, trouble-shoot, documents, import-history, admin/data-upload, `/company/:slug`.
- Live settings pages: `UserManagementPage`, `CompanyProfilePage`. Other slugs are placeholders.
- **There are no dedicated list pages** for customers, warehouses, carriers, or FC addresses. Those APIs are consumed as dropdowns on operational screens.
- Permissions hook: `useCurrentUser` + `usePermission`. Sidebar admin checks `role === "ADMIN"` only (does not use `manage_users` permission string consistently).
- Ant Design **5.27.3**, Icons 6, React 19, react-router 7. Mega menu should use `Dropdown` + `popupRender` (already started) or `Drawer` under 900px. Do not add another component library.
- Theme: primary `#2f6bff` (workbench blue). Brand orange for DLX mark is `#e38b16` / `#c45a10` / `#f3c14e`. Settings hover/active should use **DLX orange**, not invent a fourth palette.

### 3.4 Isolation reality

- **No `company_id`.** Do not add a fake tenant layer in 12.x unless product explicitly becomes multi-company.
- Isolation that exists: warehouse scope + customer scope on `User`, applied in master-data list and operational queries via `access_policy.py`.
- ADMIN bypasses scope.

### 3.5 Soft delete

Referenced masters already use `is_active`. Hard DELETE of customers/warehouses/carriers would break inbound/outbound FKs (`ondelete=RESTRICT`). Settings CRUD must **deactivate**, not delete.

### 3.6 BOL templates

BOL generation and XLSX/PDF live under picking/BOL services and `/outbound/bol`. There is no template CMS. Document Templates in the menu must wrap the **current default BOL layout**, not a parallel HTML template store, until a later phase stores override files.

---

## 4. Planned menu item status

### Column 1 — Company & Access

| Item | Status | Reuse |
|---|---|---|
| Company Profile | PARTIAL | Experimental model/API/page. Needs Alembic + audit + sidebar brand binding. |
| User Management | PARTIAL | `users` API + new page. Missing password reset UX, scope editor UI, audit on writes. |
| Access Control | PARTIAL | Roles + `Permission` enum + scope tables exist. No ACL matrix UI. SHOULD REUSE EXISTING. |
| Team Setting | ABSENT | Closest field: `WorkOrder` / exception `assigned_team` string. Defer or reuse user list + display_name groups. |
| Email Setting | ABSENT | No mail backend. SHOULD DEFER. |
| Company Code | ABSENT | Not a legal-entity table. SHOULD DEFER or fold into Company Profile. |
| Preference Setting | ABSENT | Timezone already env `BUSINESS_TIMEZONE=America/Los_Angeles`. Fold into Company Profile / user prefs. SHOULD REUSE EXISTING config. |
| Audit Log | PARTIAL | `audit_logs` table exists; no settings UI / query API. SHOULD REUSE EXISTING. |

### Column 2 — Master Data

| Item | Status | Reuse |
|---|---|---|
| Trade Party | SHOULD REUSE EXISTING | `customers` + master-data API. Need admin page, PATCH, deactivate. |
| Area Group | SHOULD REUSE EXISTING | `warehouse_areas`. Need page + PATCH. |
| Warehouse Point Group | ABSENT / map later | West Coast 仓点 is import semantics, not a table. Do not invent a second warehouse list. Document mapping in import profile. SHOULD DEFER as its own entity. |
| Warehouse | SHOULD REUSE EXISTING | `warehouses` API. Need page + PATCH. |
| Zone | SHOULD REUSE EXISTING | Same as Area (`warehouse_areas`) unless a new meaning is defined. Do not split Area vs Zone without a data rule. |
| Location | SHOULD REUSE EXISTING | `warehouse_locations` API. Need page + PATCH. |
| Service Setting | ABSENT | Outbound `OBType` enum already covers FBA/TRANSFER/PICKUP. SHOULD REUSE enum; DEFER extra table. |
| Ocean Carrier | SHOULD REUSE EXISTING | `carriers` (ocean + truck share one master today). Need page + PATCH. Optional later `mode` flag, not a second table. |
| Terminals | ABSENT | SHOULD DEFER unless container tracking needs a terminal FK. |
| Shipping Modes | SHOULD REUSE EXISTING | `OBType` + load/carrier usage. Enum UI only. |
| FC Address Book | SHOULD REUSE EXISTING | `amazon_fc_addresses` API. Need page + PATCH. |
| Exception Reasons | PARTIAL | `ExceptionType` enum + free-text on exceptions. Optional lookup table later; DEFER if enum is enough. |
| Force Majeure Events | ABSENT | SHOULD DEFER. Can tag Trouble Shoot later. |

### Column 3 — Control & Finance

| Item | Status | Reuse |
|---|---|---|
| Document Templates | PARTIAL | Default BOL/PDF/XLSX exist. Settings page should point at current generator. SHOULD REUSE EXISTING. New template files = later. |
| Numbering Rules | PARTIAL | Numbers already allocated in services (`inbound_no`, `ob_no`, `exception_no`, load/BOL). Expose read-only format first. SHOULD DEFER editable sequences until collision rules are specified. |
| Status & Workflow | PARTIAL | Status enums live on inbound/OB/picking/BOL/exceptions. Document only in 12.x. SHOULD DEFER a workflow engine. |
| Billing Codes | ABSENT | SHOULD DEFER (not WMS-critical). |
| General Ledger Codes | ABSENT | SHOULD DEFER. |
| Account Block | ABSENT | SHOULD DEFER. |
| Bank Account | ABSENT | SHOULD DEFER. |
| Commission Setting | ABSENT | SHOULD DEFER. |
| Income Statement | ABSENT | SHOULD DEFER. |
| Balance Sheet | ABSENT | SHOULD DEFER. |

Finance column is Uni Cang accounting. Yuki is a WMS. Keep menu entries visible as **Coming Soon** for ADMIN only; do not build shadow ledgers.

---

## 5. Reuse matrix

| Menu | Model | API now | Page now | 12.x action |
|---|---|---|---|---|
| User Management | User | GET/POST/PATCH | `/company/user-management` | Add scope editor, audit, permission gate |
| Company Profile | CompanyProfile | GET/PUT | `/company/company-profile` | Alembic, audit, bind brand text |
| Access Control | User + scopes + Permission | PATCH scope | none | Settings page over existing APIs |
| Trade Party | Customer | GET/POST | none | Page + PATCH + is_active |
| Warehouse | Warehouse | GET/POST | none | Page + PATCH + is_active |
| Area / Zone | WarehouseArea | GET/POST | none | One page; do not clone |
| Location | WarehouseLocation | GET/POST | none | Page + PATCH + is_active |
| Ocean Carrier | Carrier | GET/POST | none | Page + PATCH + is_active |
| FC Address Book | AmazonFCAddress | GET/POST + GET by code | none | Page + PATCH + is_active |
| Audit Log | AuditLog | writes only | none | GET /audit-logs |
| Document Templates | BOL services | generate/export | `/outbound/bol` | Settings deep-link + later override |
| Exception Reasons | ExceptionType | operational exceptions | `/trouble-shoot` | Reuse enum |

Missing PATCH on most master-data endpoints is the main API gap — not missing tables.

---

## 6. Database gaps (do not migrate in 12.0)

Allowed later, only if a page needs them:

1. `company_profiles` — promote runtime table to Alembic. Singleton `id=1`. Columns already drafted: name/brand/legal/email/phone/address/city/state/zip/country/timezone/`default_warehouse_id`.
2. Master PATCH support — no new tables; add `updated_by` only if audit JSON is insufficient.
3. Optional `carriers.mode` (`OCEAN`/`TRUCK`/`OTHER`) — only if Ocean Carrier vs truck must split in UI. Default both visible.
4. Do **not** add `companies`, `gl_accounts`, `bank_accounts`, `billing_codes`, `terminals`, `force_majeure_events` in 12.1–12.3.
5. Do **not** add `company_id` to operational tables in 12.x.

---

## 7. Suggested frontend routes

Keep left nav operational. Settings live under `/settings`.

```
/settings                         hub (optional)
/settings/company-profile
/settings/users
/settings/access
/settings/audit-log
/settings/customers               Trade Party
/settings/warehouses
/settings/areas
/settings/locations
/settings/carriers
/settings/fc-addresses
/settings/documents               deep-link + BOL template note
/company/:slug                    temporary aliases; redirect in 12.1
```

Coming Soon items route to a single `SettingsUnavailablePage` with reason = DEFER.

---

## 8. Mega Menu component plan

Reuse `frontend/src/components/CompanyMenu.tsx`.

- Trigger: existing top-right gear (keep circle button).
- Desktop: Ant Design 5 `Dropdown` + `popupRender`, panel `min-width: 900px; max-width: 1000px`, 3 CSS columns, white rounded card, shadow.
- Hover/active: DLX orange (`#e38b16`), not blue primary.
- Close: click outside (Dropdown default) + Esc.
- `<900px`: same catalog in `Drawer`.
- Hide items the user cannot read (`manage_users` / ADMIN for access; finance Coming Soon hidden from VIEWER).
- Coming Soon items visible to ADMIN/MANAGER with a muted label; click opens placeholder.
- Do not change sider operational grouping.

Catalog should be one module (`companyCatalog` / `settingsCatalog`) consumed by menu + router.

---

## 9. RBAC matrix (target)

Existing permission strings: `read`, `manage_inbound`, `manage_outbound`, `manage_warehouse`, `manage_users`.

| Capability | ADMIN | MANAGER | INBOUND | OUTBOUND | WAREHOUSE | VIEWER |
|---|---|---|---|---|---|---|
| Open Settings menu | Y | Y | limited | limited | limited | N |
| Users / Access Control | Y | N | N | N | N | N |
| Company Profile write | Y | N | N | N | N | N |
| Company Profile read | Y | Y | Y | Y | Y | N |
| Master data write (customer/wh/carrier/FC/area/location) | Y | Y* | N | N | N | N |
| Master data read | Y | Y | Y | Y | Y | Y (scoped) |
| Audit log | Y | Y | N | N | N | N |
| Finance Coming Soon | Y | N | N | N | N | N |

\* Recommend MANAGER write on masters in 12.2; today POST masters are ADMIN-only. Changing that is a conscious 12.2 decision.

Frontend and FastAPI must both enforce. Page hide is not security.

Suggested new permission only if needed: `manage_settings`. Prefer extending `manage_users` + existing admin dependency rather than a seventh role.

---

## 10. Audit log design

Reuse `audit_logs`:

- `action`: CREATE / UPDATE / DEACTIVATE / SCOPE_CHANGE / LOGIN (optional later)
- `entity_type`: USER, CUSTOMER, WAREHOUSE, AREA, LOCATION, CARRIER, FC_ADDRESS, COMPANY_PROFILE
- `entity_id`, `before_data`, `after_data`, `user_id`, `created_at`

12.1–12.2 work:
- Shared helper `write_audit(db, user, action, entity_type, entity_id, before, after)` used by user PATCH and master PATCH.
- `GET /api/v1/audit-logs` admin/manager, filter by entity_type, entity_id, user_id, date.
- Settings page table. Do not create `settings_audit_logs`.

---

## 11. Linkage to operations

| Domain | Settings dependency |
|---|---|
| Inbound | customer, warehouse, location, import 仓点 mapping |
| Inventory | warehouse, location, area |
| FBA | FC address book, customer, warehouse |
| Outbound / Dispatch | customer, warehouse, carrier, OBType, FC |
| Picking | warehouse, location, users as assignees |
| BOL | warehouse ship-from, FC ship-to, carrier, default template |
| Container Tracking | carrier (optional), warehouse, customer |
| Work orders / Trouble Shoot | users, warehouse, exception types |
| West Coast import | customers + warehouses + 仓点 gate before bulk OL |

Deactivating a customer/warehouse/carrier must block new documents but keep historical FKs.

---

## 12. Safe implementation sequence

| Phase | Intent | Migrations? |
|---|---|---|
| **12.0** | This assessment | No |
| **12.1** | Settings shell: catalog, mega menu polish (orange, drawer, Coming Soon), route aliases, **Alembic for company_profiles only if keeping that table**, audit helper + company profile writes | Yes, one small revision if profile kept |
| **12.2** | Master data admin pages that wrap existing APIs: customers, warehouses, areas, locations, carriers, FC. Add PATCH + is_active. No new tables. | Only if PATCH needs no schema — then **no** migration |
| **12.3** | Access Control UI (role + warehouse/customer scope) on existing user APIs. Audit those writes. | No |
| **12.4** | Audit Log page + GET API over `audit_logs`. | No |
| **12.5** | Document Templates settings surface for default BOL; numbering read-only. | No |
| **12.6** | Decide finance/email/terminals/force majeure: still Coming Soon unless a real WMS rule appears. | Defer |

Do not start 12.2 while the local merge is open.

---

## 13. PHASE 12.1 exact file list (planned, not done now)

Create/modify later:

- `frontend/src/components/CompanyMenu.tsx` — catalog-driven, orange hover, Coming Soon, permission hide, narrow Drawer
- `frontend/src/pages/companyCatalog.ts` — align labels to the 3 columns in this doc
- `frontend/src/App.tsx` — `/settings/*` routes + redirects from `/company/:slug`
- `frontend/src/pages/CompanySettingsPage.tsx` — router only
- `frontend/src/pages/CompanyProfilePage.tsx` — keep; bind save errors
- `frontend/src/pages/UserManagementPage.tsx` — already live; only touch if audit/scope needed in 12.1 (prefer 12.3)
- `frontend/src/styles.css` or `motion.css` — mega panel 900–1000px, orange hover
- `backend/app/api/v1/endpoints/company_profile.py` — remove silent `create(checkfirst)` once Alembic exists
- `backend/alembic/versions/YYYYMMDD_00xx_company_profile.py` — **12.1 only**, after merge is clean
- `backend/app/services/audit.py` — thin wrapper around `AuditLog`
- `docs/CURRENT_SYSTEM_SETTINGS_ASSESSMENT.md` — this file (already)

Do not touch inbound/outbound/inventory services in 12.1.

---

## 14. Risks, compatibility, rollback

| Risk | Mitigation |
|---|---|
| Local unfinished merge + mixed UI experiments | 12.1 on clean `main` or finished merge commit only |
| `company_profiles` not in Alembic | Stop runtime DDL; add revision or drop table and recreate via Alembic |
| Duplicate masters (Trade Party vs customers) | Reuse `customers`; menu label only |
| Area vs Zone duplication | One model (`warehouse_areas`) until a written difference exists |
| Carrier ocean vs truck | Same `carriers` table |
| Finance menu creating fake books | Coming Soon, no tables |
| Admin-only master POST vs MANAGER need | Explicit 12.2 decision; keep ADMIN until then |
| Audit gaps | No settings write without `AuditLog` row |
| Hard delete of referenced masters | API refuses DELETE; only `is_active=false` |
| Front-only permission hide | FastAPI `require_admin` / permission checks remain |
| Rollback 12.1 | revert menu/CSS/routes; downgrade only the company_profile revision; operational tables untouched |

---

## 15. Recommended next cut

**PHASE 12.1 — Settings shell + Company Profile promotion**

Preconditions:
1. Local merge closed (`git status` clean or a single merge commit).
2. `alembic current` == `20260830_0020` on the server DB.
3. No parallel master-data tables designed.

12.1 outcome: gear menu matches the three columns above, unusable items say Coming Soon, Company Profile is a real migrated singleton with audit, existing User Management remains the only other live editor.
