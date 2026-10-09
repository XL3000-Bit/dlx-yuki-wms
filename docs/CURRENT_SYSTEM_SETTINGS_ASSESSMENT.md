# Phase 12.0 — System Settings & Master Data Assessment

Assessment date: 2026-09-02

Repository: `C:\Users\XL\dlx-yuki-wms`

Branch: `feature/java-api-parity`
Scope: assessment only. No business code, schema migration, database data, dependency, or runtime configuration was changed.

## 1. Executive conclusion and actual Alembic state

The repository already has useful settings foundations: a three-column settings catalog, Company Profile, user administration, role/scope enforcement, core master models and read/create APIs, and an operational audit writer. It does **not** yet have a complete system-settings product. Most menu entries are routing placeholders, master data lacks lifecycle editing, audit data has no settings UI/query API, and several proposed finance/configuration concepts do not exist in the WMS domain.

Phase 12 should extend existing domain objects rather than create parallel “settings” copies. The next implementation cut must first stabilize migrations and backend ownership.

Actual Alembic evidence:

- Source has **two heads**: `20260831_0024` and `20260901_0021`.
- Connected PostgreSQL reports current revisions `20260830_0023` and `20260901_0021`.
- Therefore the database has the Company Profile branch applied, but the scan/staging branch is one revision behind source (`20260831_0024` is not applied).
- `20260901_0021_company_profile.py` branches from `20260830_0020`; `20260831_0024_staging_load_verification.py` descends from `20260830_0023`.
- This is a Phase 12.1 gate. A reviewed merge revision and controlled database upgrade are required before any new settings migration. This assessment does not create or apply either.

## 2. Git status and pre-existing uncommitted work

The working tree was already dirty before this assessment. Those changes were treated as user-owned and left untouched. Baseline `git status --short`:

```text
 M backend-java/README.md
 M backend-java/pom.xml
 M backend-java/src/main/java/com/dlxyuki/wms/WmsApplication.java
 M backend-java/src/main/java/com/dlxyuki/wms/config/AppProperties.java
 M backend-java/src/main/java/com/dlxyuki/wms/config/DatabaseConfig.java
 M backend-java/src/main/java/com/dlxyuki/wms/config/SecurityConfig.java
 M backend-java/src/main/java/com/dlxyuki/wms/fba/FbaController.java
 M backend-java/src/main/java/com/dlxyuki/wms/fba/FbaRepository.java
 M backend-java/src/main/java/com/dlxyuki/wms/fba/FbaService.java
 M backend-java/src/main/resources/application.yml
 M backend/app/api/v1/router.py
 M backend/app/models/__init__.py
 M frontend/src/App.tsx
 M frontend/src/layouts/AppLayout.tsx
?? backend-java/docs/
?? backend-java/src/main/java/com/yuki/
?? backend-java/src/main/resources/mapper/
?? backend-java/src/test/java/com/dlxyuki/wms/fba/FbaAllocationWriteContractTest.java
?? backend-java/src/test/java/com/dlxyuki/wms/fba/FbaWriteContractTest.java
?? backend-java/src/test/java/com/yuki/
?? backend/app/api/v1/endpoints/threepl.py
?? backend/app/schemas/threepl.py
?? backend/app/services/threepl.py
?? backend/tests/test_threepl.py
?? docs/PDA_PROJECT_KICKOFF.md
?? frontend/src/api/threepl.ts
?? frontend/src/components/pda/
?? frontend/src/pages/PdaPage.tsx
?? frontend/src/pages/ThreePLPage.tsx
?? frontend/src/pages/pda.css
?? frontend/src/threepl.css
?? login-night-city-after.png
?? nginx/
?? wallboard-after.png
```

The only file intentionally changed by Phase 12.0 is this document. In particular, the existing `frontend/src/App.tsx`, `frontend/src/layouts/AppLayout.tsx`, API router, Java parity work, PDA, and 3PL work were not edited.

## 3. Existing functionality and models

### Backend domain

- `CompanyProfile` exists, with company/brand/legal name, contact/address fields, timezone, and default warehouse. Its migration is `20260901_0021`; it is not an unmigrated runtime table.
- `User` supports roles `ADMIN`, `MANAGER`, `INBOUND`, `OUTBOUND`, `WAREHOUSE`, and `VIEWER`, active state, customer/warehouse scope modes, and many-to-many scope assignments.
- Existing reusable masters are `Customer`, `Warehouse`, `WarehouseArea`, `WarehouseLocation`, `Carrier`, and `AmazonFCAddress`; all already expose `is_active`.
- Operational types already encode some proposed configuration semantics: outbound types, delivery/truck fields, exception types/free text, document records, BOL generation, status enums, and workflow transitions.
- `AuditLog` records actor, action, entity type/id, before/after JSON, and timestamp. Operational services already write audit records.

### API reality

- FastAPI exposes authenticated Company Profile GET and ADMIN PUT, ADMIN user management/scope endpoints, and master GET/POST endpoints.
- Master reads are scope-aware for customers, warehouses, areas, and locations. Carriers and FC addresses are global.
- Master data currently has no PATCH/deactivate workflow, hard-delete API, consistent pagination/sorting, or complete audit coverage.
- Java exposes the same `/api/v1` namespace for users and generic master-data reads/creates, but Company Profile is GET-only. The untracked Java v2 code advertises additional read-only reporting/master endpoints.
- Two implementations therefore serve overlapping contracts with unequal behavior. A single settings write owner must be selected; dual writes would invite drift.

### Data isolation and lifecycle

- No `company_id`/tenant key exists. The current architecture is single-company, with access isolation supplied by warehouse/customer scopes.
- Master codes are globally unique, which is coherent only while the system remains single-company.
- Historical operational foreign keys generally protect masters with restrictive behavior, but warehouse area/location relationships use cascading behavior. That must be reviewed before exposing any deletion capability.
- There are no master DELETE endpoints today. The safe product direction is deactivate/reactivate via `is_active`, never hard-delete referenced masters.

## 4. Menu-by-menu assessment

Status vocabulary: **EXISTS** means a usable vertical slice exists; **PARTIAL** means a reusable foundation exists but the settings experience is incomplete; **ABSENT** means no matching durable capability exists; **SHOULD REUSE EXISTING** forbids a parallel model; **SHOULD DEFER** means requirements/domain ownership are not mature enough to implement safely.

| Group | Menu item | Status | Assessment |
|---|---|---|---|
| Company & Access | Company Profile | EXISTS / PARTIAL | GET/PUT and page exist; singleton integrity, read purity, field breadth, Java write parity, and error handling remain incomplete. |
| Company & Access | User Management | EXISTS / PARTIAL | List/create/role/active work; scope editor, search, paging, full edit flow, and audit coverage are missing. |
| Company & Access | Access Control | PARTIAL / SHOULD REUSE EXISTING | Reuse role permissions plus customer/warehouse scopes; no separate policy engine is justified yet. |
| Company & Access | Team Setting | PARTIAL / SHOULD REUSE EXISTING | Reuse users if “team” only means roster/grouping; defer a Team table until membership semantics are defined. |
| Company & Access | Email Setting | ABSENT / SHOULD DEFER | No provider, template, secrets, delivery, bounce, or ownership model. |
| Company & Access | Company Code | ABSENT / SHOULD REUSE EXISTING | Add to Company Profile only after format/immutability/import rules are agreed. |
| Company & Access | Preference Setting | PARTIAL / SHOULD REUSE EXISTING | Timezone exists on Company Profile; locale, units, date format, and page-size preferences do not. |
| Company & Access | Audit Log | PARTIAL / SHOULD REUSE EXISTING | Writer/model exist; query API, UI, request metadata, master/user coverage, and retention policy are missing. |
| Master Data | Trade Party | PARTIAL / SHOULD REUSE EXISTING | Customer is the existing party master; do not duplicate it until supplier/vendor roles are real requirements. |
| Master Data | Area Group | PARTIAL / SHOULD REUSE EXISTING | Reuse `WarehouseArea`; clarify whether this label differs from Zone. |
| Master Data | Warehouse Point Group | ABSENT / SHOULD REUSE EXISTING | Start from warehouse/location hierarchy; defer a new grouping entity until routing semantics exist. |
| Master Data | Warehouse | PARTIAL / SHOULD REUSE EXISTING | Model and read/create APIs exist; edit, deactivate, validation, paging, and UI are missing. |
| Master Data | Zone | PARTIAL / SHOULD REUSE EXISTING | Reuse `WarehouseArea`; do not create a second zone hierarchy. |
| Master Data | Location | PARTIAL / SHOULD REUSE EXISTING | Model and filtered reads/create exist; lifecycle UI/API and referential safeguards are incomplete. |
| Master Data | Service Setting | PARTIAL / SHOULD REUSE EXISTING | Some behavior exists in outbound/delivery fields; no canonical service registry or pricing semantics exist. |
| Master Data | Ocean Carrier | PARTIAL / SHOULD REUSE EXISTING | Reuse `Carrier`; modal specificity and lifecycle fields need definition. |
| Master Data | Terminals | ABSENT / SHOULD DEFER | No terminal domain, relationships, or operational consumer exists. |
| Master Data | Shipping Modes | PARTIAL / SHOULD REUSE EXISTING | Existing outbound/delivery/truck concepts overlap; normalize semantics before adding a table. |
| Master Data | FC Address Book | PARTIAL / SHOULD REUSE EXISTING | Reuse `AmazonFCAddress`; add lifecycle/search/edit UI rather than a new address model. |
| Master Data | Exception Reasons | PARTIAL / SHOULD REUSE EXISTING | Exception enums and free text exist; a configurable catalog needs mapping and reporting rules first. |
| Master Data | Force Majeure Events | ABSENT / SHOULD DEFER | No WMS workflow currently consumes this concept. |
| Control & Finance | Document Templates | PARTIAL / SHOULD REUSE EXISTING | Existing operational documents/BOL generator are integration points; versioned templating is absent. |
| Control & Finance | Numbering Rules | PARTIAL / SHOULD REUSE EXISTING | Number generation exists in services; configurable, concurrency-safe rules do not. |
| Control & Finance | Status & Workflow | PARTIAL / SHOULD REUSE EXISTING | Reuse enums and transition logic; arbitrary workflow configuration is high-risk and not yet modeled. |
| Control & Finance | Billing Codes | ABSENT / SHOULD DEFER | No billing ledger or rated service domain. |
| Control & Finance | General Ledger Codes | ABSENT / SHOULD DEFER | Accounting ownership/integration is undefined. |
| Control & Finance | Account Block | ABSENT / SHOULD DEFER | A customer hold may eventually fit, but block types and enforcement points are undefined. |
| Control & Finance | Bank Account | ABSENT / SHOULD DEFER | Sensitive finance data is outside the current WMS boundary. |
| Control & Finance | Commission Setting | ABSENT / SHOULD DEFER | No commission parties, events, or settlement model. |
| Control & Finance | Income Statement | ABSENT / SHOULD DEFER | This is a finance/reporting product, not current WMS configuration. |
| Control & Finance | Balance Sheet | ABSENT / SHOULD DEFER | This is a finance/reporting product, not current WMS configuration. |

## 5. Reuse matrix

| Requested concept | Reuse first | Required extension, if approved |
|---|---|---|
| Company identity/code/preferences | `CompanyProfile` | Singleton enforcement, company code and selected display defaults. |
| Access Control | `User`, role-permission mapping, user scope tables, `access_policy.py` | Permission-derived UI and scope editing; avoid a second ACL store. |
| Team | `User` roster | Add Team only with defined ownership/membership/use cases. |
| Trade Party | `Customer` | Add party roles only when non-customer parties enter workflows. |
| Area Group / Zone | `WarehouseArea` | Settle one product term and expose lifecycle endpoints/UI. |
| Warehouse Point Group | `Warehouse` + `WarehouseLocation` | Add grouping only for a proven routing/picking requirement. |
| Ocean Carrier | `Carrier` | Mode/type fields if genuinely needed. |
| Shipping Modes / Services | Existing outbound type and delivery semantics | Normalize vocabulary and consumers before persistence. |
| FC Address Book | `AmazonFCAddress` | Edit/deactivate/search and scoped presentation. |
| Exception Reasons | Existing exception types and reason text | Optional governed catalog with backward-compatible snapshots. |
| Documents | Existing document records and BOL generator | Versioned templates/rendering contract. |
| Numbering | Existing service number generators | One concurrency-safe numbering service, not per-page counters. |
| Status / Workflow | Existing enums and transition services | Start read-only; configurable transitions only after invariants are cataloged. |
| Audit Log | Existing `AuditLog` and audit service | Read API/UI, metadata, coverage, retention. |

## 6. Database gaps and schema suggestions — no migration in this phase

1. Resolve the two Alembic heads before authoring new revisions. Create a merge revision only after reviewing both branches and test upgrade/downgrade on a copy of production-like data.
2. Make Company Profile singleton behavior explicit at the database level. The current “select first row” convention can silently permit duplicates. A fixed singleton key or equivalent unique constraint is preferable.
3. If approved, extend Company Profile with a stable company code and only proven preferences such as default weight unit, date format, locale, and page size. Keep secrets out of this row.
4. Keep existing `is_active` lifecycle fields and add PATCH/deactivate APIs. Never hard-delete a master referenced by operations. Review CASCADE behavior on areas/locations before exposing lifecycle mutations.
5. Add consistent `created_at`/`updated_at` and, if concurrent admin edits are credible, optimistic version checks to mutable settings masters.
6. Extend audit records with request/correlation ID, source, IP/user-agent where policy permits, plus indexes for `(created_at, id)`, `(entity_type, entity_id, created_at)`, and `(user_id, created_at)`. Add `company_id` only as part of an intentional tenancy project.
7. Do not casually add `company_id`. If multi-company is a real requirement, introduce a first-class Company/Organization boundary, company-scoped foreign keys, composite uniqueness such as `(company_id, code)`, query guards, migration/backfill, and tests across every operational table. Otherwise document and enforce the singleton deployment model.
8. Do not create tables yet for teams, terminals, force majeure, email delivery, finance, configurable workflows, or generalized service catalogs without owners, consumers, invariants, and retention/security rules.

## 7. Frontend routes and page inventory

- Canonical settings route: `/settings/:slug`.
- Compatibility alias: `/company/:slug`.
- Live pages: `company-profile` and `users`.
- Every other catalog item renders the shared Company Settings “Coming Soon” shell.
- Company Profile uses React Query directly against `/company-profile`; users use `frontend/src/api/users.ts`; master data currently has read clients only in `frontend/src/api/masterData.ts`.
- The application uses React 19, React Router 7, Ant Design 5, React Query, and Zustand. Global Ant Design configuration uses compact components, primary blue, navy navigation, and disabled motion.
- The current CSS minimum width of 1180px means the settings experience is not truly mobile even though the menu switches to an Ant Design Drawer below the medium breakpoint.
- `frontend/src/App.tsx` and `frontend/src/layouts/AppLayout.tsx` contain pre-existing uncommitted PDA/3PL work and must remain outside the first settings cut unless route integration is strictly necessary and coordinated.

## 8. Three-column mega-menu structure

Keep one catalog as the source of truth and render these three columns:

1. **Company & Access** — Company Profile, User Management, Access Control, Team Setting, Email Setting, Company Code, Preference Setting, Audit Log.
2. **Master Data** — Trade Party, Area Group, Warehouse Point Group, Warehouse, Zone, Location, Service Setting, Ocean Carrier, Terminals, Shipping Modes, FC Address Book, Exception Reasons, Force Majeure Events.
3. **Control & Finance** — Document Templates, Numbering Rules, Status & Workflow, Billing Codes, General Ledger Codes, Account Block, Bank Account, Commission Setting, Income Statement, Balance Sheet.

Current behavior is close to the target presentation: the gear opens a desktop dropdown and compact Drawer. Gaps:

- Company name is not an alternate trigger.
- Access filtering uses hard-coded role strings; it should consume authoritative permissions/capabilities.
- `VIEWER` cannot see the menu, although authenticated direct routes can still view Company Profile. Visibility and route authorization need one policy.
- Placeholder links look equally real to live features. Deferred entries should be visibly disabled/roadmapped, or omitted until approved.
- Keyboard focus, escape/close behavior, overflow, active-page indication, and 1180px/mobile behavior need explicit accessibility/responsive tests.

## 9. RBAC and scope matrix

Backend authorization remains authoritative; menu hiding is only presentation.

| Capability | ADMIN | MANAGER | INBOUND | OUTBOUND | WAREHOUSE | VIEWER |
|---|---:|---:|---:|---:|---:|---:|
| Read permitted operational/scoped data | Yes | Yes | Yes | Yes | Yes | Yes |
| Manage inbound | Yes | Yes | Yes | No | Yes | No |
| Manage outbound | Yes | Yes | No | Yes | Yes | No |
| Manage warehouse operations | Yes | Yes | Yes | No | Yes | No |
| Manage users/scopes | Yes | No | No | No | No | No |
| View Company Profile | Yes | Yes | Yes | Yes | Yes | Yes |
| Edit Company Profile | Yes | No | No | No | No | No |
| View scoped master data | Yes | Yes | Yes | Yes | Yes | Yes |
| Create/edit/deactivate master data | Yes | No | No | No | No | No |
| View Audit Log | Yes | No by default | No | No | No | No |
| Change system controls | Yes | No | No | No | No | No |

Recommended rules:

- Preserve existing customer/warehouse scope modes on every scoped master query and mutation.
- Use permission checks rather than frontend role comparisons; add granular settings permissions only when ADMIN-only becomes too coarse.
- Keep self-demotion/self-deactivation protection and add audit events for user, scope, role, and active-state changes.
- Decide whether MANAGER receives read-only Audit Log access through an explicit permission, not an implicit role shortcut.

## 10. Audit Log assessment

The existing model/service should be expanded, not replaced. It already captures meaningful before/after operational state for inbound, inventory, outbound, import, FBA, picking, BOL, and Company Profile actions.

Required gaps before an Audit Log settings page is considered complete:

- ADMIN-only paginated query endpoint with stable cursor/order.
- Filters for date range, actor, action, entity type, entity ID, and optionally warehouse/customer where derivable.
- Coverage for user creation, role/active/scope changes, and every settings/master mutation.
- Request/correlation metadata and explicit source (`ui`, `api`, `import`, `system`).
- Redaction policy for credentials, tokens, personal data, and future finance fields.
- Retention/export policy; audit rows should be append-only to ordinary application roles.
- A detail drawer that renders structured before/after JSON safely, without interpreting stored HTML.

## 11. Integration points and contract boundaries

- Master foreign keys feed inbound, inventory, outbound, FBA, picking, BOL, documents, and dashboards. Deactivation must preserve historical labels/IDs and block invalid new assignments.
- Imports rely on master codes/aliases and must share validation with UI/API writes.
- Company Profile default warehouse must respect warehouse active state and user scope when presented, while remaining an organization default rather than a per-user authorization grant.
- User scope enforcement in access-policy code must be applied identically by FastAPI and Java endpoints.
- FastAPI and Spring Boot currently overlap under `/api/v1`. Select one write owner, document routing, and add contract/parity tests before expanding settings mutations. Java Company Profile currently lacks PUT, so it cannot silently be treated as equivalent.
- The FastAPI Company Profile GET currently creates a row when none exists and converts broad exceptions into a “migration missing” response. Reads should become side-effect free and errors should preserve their real class.
- React Query keys and invalidation should be centralized per settings resource so edits refresh menus, selectors, and operational screens consistently.
- Generic `POST /master-data/{kind}` behavior needs resource-specific validation, authorization, uniqueness-conflict mapping, and audit semantics before broader exposure.

## 12. Recommended implementation sequence: 12.1–12.6

### 12.1 — Foundation stabilization and ownership gate

- Reconcile Alembic heads and bring the connected database to the reviewed source head.
- Select and document the sole `/api/v1` settings write owner; define Java/FastAPI parity expectations.
- Enforce Company Profile singleton/read purity and truthful error handling.
- Complete audit coverage for Company Profile, users/scopes, and future master writes.
- Add contract/RBAC tests before adding menu breadth.

Exit gate: one migration lineage, one settings write owner, repeatable Company Profile tests, and no unaudited ADMIN mutation.

### 12.2 — Core master lifecycle

- Build list/search/page/edit/deactivate/reactivate flows for Customer/Trade Party, Warehouse, Area/Zone, Location, Carrier, and FC Address.
- Reuse existing tables, scopes, codes, and operational selectors.
- Reject hard deletion and active references to inactive parents.

### 12.3 — Access Control and scope UX

- Add scope editing, search/paging, and full user edit UX.
- Drive navigation and routes from capability checks.
- Decide Team semantics; implement only if it has a real workflow consumer.

### 12.4 — Audit and guarded controls

- Deliver paginated Audit Log API/page/detail view with redaction and retention policy.
- Surface Numbering Rules and Status/Workflow initially as read-only diagnostics of existing behavior.

### 12.5 — Selected operational configuration

- Only after domain workshops, normalize Service Setting, Shipping Modes, Exception Reasons, and Document Templates.
- Add integration tests proving operational consumers and imports use the same configuration.

### 12.6 — Deferred-domain decision

- Reassess Email, Terminals, Force Majeure, Billing/GL, Account Block, Bank Account, Commission, Income Statement, and Balance Sheet.
- Keep them disabled/absent unless ownership, compliance, accounting integration, and concrete workflows are approved.

## 13. Exact recommended next cut files

The next cut is **12.1 only**, not a broad master-data implementation.

Files expected to be reviewed/changed:

- `backend/alembic/versions/<new_revision>_merge_system_settings_heads.py` — new reviewed merge revision; do not rewrite applied history.
- `backend/app/models/company_profile.py`
- `backend/app/api/v1/endpoints/company_profile.py`
- `backend/app/api/v1/endpoints/users.py`
- `backend/app/api/v1/endpoints/masters.py`
- `backend/app/services/audit.py`
- `backend/tests/test_company_profile.py` — new focused contract/RBAC/singleton tests.
- `backend/tests/test_system_settings_rbac.py` — new cross-resource authorization tests.
- `backend-java/src/main/java/com/dlxyuki/wms/companyprofile/CompanyProfileController.java`
- `backend-java/src/main/java/com/dlxyuki/wms/companyprofile/CompanyProfileRepository.java`
- `backend-java/src/main/java/com/dlxyuki/wms/user/UserController.java`
- `backend-java/src/main/java/com/dlxyuki/wms/master/MasterDataController.java`
- `frontend/src/pages/CompanyProfilePage.tsx`
- `frontend/src/pages/UserManagementPage.tsx`
- `frontend/src/components/CompanyMenu.tsx`
- `frontend/src/pages/companyCatalog.ts`
- `frontend/src/api/users.ts`

Files that should **not** enter 12.1 unless the owner/routing decision requires a minimal integration edit: `frontend/src/App.tsx`, `frontend/src/layouts/AppLayout.tsx`, PDA/3PL files, finance pages, new master tables, and operational services.

Before implementation, reconcile this list with the dirty working tree and isolate Phase 12 work in its own branch/commit series without discarding existing changes.

## 14. Risks, verification, and rollback

### Principal risks

- Two Alembic heads plus a live database one revision behind one branch make new migrations unsafe until reconciled.
- FastAPI and Java overlap at `/api/v1` but do not have feature parity; unspecified write ownership can create behavior and audit drift.
- Company Profile GET mutates state and masks unrelated database errors as migration errors.
- Frontend role-string checks disagree with direct-route/backend capability behavior.
- Global uniqueness and absence of `company_id` make accidental “partial multi-tenancy” especially dangerous.
- Cascading area/location relationships conflict with a strict no-hard-delete policy.
- Generic master creation lacks full resource-specific validation, lifecycle behavior, pagination, and audit coverage.
- A 31-entry mega-menu can overpromise placeholders and is constrained by the application’s 1180px minimum width.
- The pre-existing dirty tree raises accidental-overwrite and attribution risk.

### Rollback and delivery strategy

- Deliver one vertical slice per commit, with migrations separated from API/UI changes and tested upgrade/downgrade paths.
- Never rewrite an applied migration; merge lineages forward.
- Prefer reversible `is_active` transitions and preserve historical foreign keys/snapshots.
- Gate new settings UI behind route/catalog status until backend ownership and contracts are deployed.
- Snapshot and verify production-like data before schema changes; roll back application deployment before attempting a reviewed migration downgrade.
- For this assessment itself, rollback is simply reverting `docs/CURRENT_SYSTEM_SETTINGS_ASSESSMENT.md`; no runtime or database rollback is needed.

Verification required for Phase 12.0: `git status --short` must show only this document as the intentional new delta beyond the recorded baseline, and `git diff --check` must pass. No application test suite is necessary because no executable code changed.
