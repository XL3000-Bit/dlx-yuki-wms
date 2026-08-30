# EasyFreight → DLX Yuki WMS GAP Analysis

**Analysis date:** 2026-08-29  
**Mode:** source and document analysis only; no EasyFreight website access, Playwright execution, or source reuse.

## 1. Scope and evidence

This assessment was made from the current DLX source tree (`frontend`, `backend/app`, `backend/alembic`, `backend/tests`, `backend/scripts`, and `docs`) and only the ten authorized EasyFreight analysis documents. EasyFreight behavior below means behavior observed in those reports; it does not imply knowledge of EasyFreight's backend or source code.

DLX verification included routes, pages, API clients, FastAPI endpoints, services, SQLAlchemy models, Alembic revisions, imports, scripts, and tests. The current backend suite passes **74/74 tests** (`pytest -q -p no:cacheprovider`). The frontend has a production build configuration but no component/unit test runner.

Status vocabulary:

- **EXISTING** — an end-to-end or materially usable implementation exists.
- **PARTIAL** — some model/API/UI behavior exists, but the operational workflow is incomplete.
- **MISSING** — no meaningful implementation was found in the current source.

Priority is `P0`–`P3`; complexity is `S`–`XL`.

## 2. Current DLX implementation and PHASE state

The README and health endpoint still identify PHASE 7, but the code and migrations have progressed further. The most accurate current description is **PHASE 1–8 implemented, followed by Container Tracking and PHASE 9.5 Dispatch Intelligence, with documentation/version metadata lagging behind**.

| Area | Status | Current evidence |
|---|---|---|
| Platform/authentication | EXISTING | FastAPI/PostgreSQL/React; password hashing; access and refresh JWTs; single-flight frontend refresh and retry; admin bootstrap; six coarse roles. |
| Inbound | EXISTING | Search/filter/pagination, create/edit, status flow, Excel template/export/import, receive-to-inventory. |
| Inventory | EXISTING | Lot ledger, locations, aging priority, server filters, export, move/adjust/hold/release, immutable transactions and audit writes. |
| FBA | EXISTING | Shipment lifecycle, FC address lookup, inventory allocation/release, import/export, workbench, selected export, batch actions, Outbound/Picking/BOL linkage. |
| Outbound Dispatch Workbench | EXISTING | Status counts, summary, multi-filter table, allocation/release, scheduling, exception state, batch actions, selected export, detail/workflow panes. |
| Splitter | EXISTING | Persistent horizontal and vertical resizable split layouts with reset behavior in the Outbound Workbench. |
| Picking | PARTIAL | Snapshot picking lists, list/history routes, XLSX output and quantity completion; no assignment, wave, scan, location confirmation, or exception workflow. |
| BOL | PARTIAL | Outbound-generated BOL snapshots and PDF/XLSX downloads; no grouped/multi-order BOL, POD workflow, upload/request/status lifecycle, or document repository. |
| Container Tracking | PARTIAL | CSV import, CNTR/MBL/HBL and milestone model, filters, URL state, detail drawer, derived earliest outbound/priority/readiness and related OB links; no normal edit/event workflow or full pickup/delivery/POD chain. |
| Excel Import | EXISTING | Six-step wizard, sheet/profile detection, mapping, validation, progress, errors, reconciliation, duplicate strategy, row fingerprints and provenance. |
| Selected Export | EXISTING | Selected-row export in FBA and Outbound workbenches. |
| Customer/carrier masters | PARTIAL | Models and admin-protected create/list APIs exist; no management UI, update lifecycle, scope, rate, terms, or performance data. |
| RBAC | PARTIAL | Backend role gates exist for admin, warehouse write, and outbound write; no permission entities, warehouse/customer scopes, or role-aware navigation/actions. |
| KPI/accounting | MISSING | No dashboard/KPI, service-order, AR/AP, payment, quote, storage billing, or accounting integration model/API/page. |

## 3. Detailed GAP matrix

| Feature | EasyFreight observed behavior | DLX current implementation | Gap | Recommended change | Frontend impact | Backend impact | Database impact | Priority | Complexity |
|---|---|---|---|---|---|---|---|---|---|
| 1. Outbound | Dense OutBound and WHS Alert/BOL operations organized around OB, BOL, appointments, carrier, POD, lifecycle tabs and counts. | **EXISTING:** mature order workbench with lifecycle actions, allocations, schedule/appointment fields, exceptions, summary/counts, batch actions, selected export and persistent split panes. | Still order-centric; no grouped BOL planning, carrier notification, POD status, configurable columns, or dedicated pre-dispatch load view. | Extend the existing workbench with a load/grouping layer, grouped BOL planning, document/POD state and saved column preferences. Preserve current allocation/status services. | Add load/group view, POD/document columns, column chooser and group actions. | Add grouping/readiness/count endpoints and orchestration without replacing existing OB APIs. | Add load/group association, document state and user column preferences. | P0 | L |
| 2. FBA | EasyFreight reports channel-aware FBA/FBM fields and pending-shipout analytics; detailed FBA execution is not directly observed. | **EXISTING:** FBA shipment lifecycle, FC resolution, atomic inventory allocation/release, imports, workbench stages, batch actions, selected export and direct Outbound/Picking/BOL flow. | Limited appointment/carrier coordination and no Amazon event/document ingestion; one FBA shipment effectively leads to an order rather than richer consolidation. | Keep the strong FBA core; add appointment exceptions, reference normalization, load consolidation and external-status integration points only where operationally needed. | Add exception flags, appointment history and consolidation visibility. | Add event adapter boundary and consolidation queries. | Add external event/reference history and optional load link. | P1 | M |
| 3. Load Management | Load is the cross-module control-tower entity with CNTR/MBL/BOL/customer/WHS/status/milestones; operational and accounting load lists exist. | **MISSING:** related data is split among inbound, container tracking, inventory, FBA, OB and BOL; no canonical Load model or page. | No shared lifecycle/identity for one physical/commercial movement; duplicated references cannot be reliably reconciled. | Introduce a lightweight canonical Load aggregate and reference links, then build a read-first control tower. Do not merge existing domain tables. | New Load Control Tower with lifecycle tabs, counts and drill-through links. | Load search/detail/count APIs and reference-link service. | New `loads` and `load_references`/association tables; indexed normalized references. | P0 | XL |
| 4. Warehouse Work Order | Explicit WO number, type, urgency, review/status, warehouse/customer/shipment references, operator and timestamps, with counts and lifecycle tabs. | **MISSING:** picking lists are specialized execution snapshots; inbound/outbound actions are not generic warehouse tasks. | No common task queue for unload, put-away, move, count, pick, load, inspection, rework or document follow-up. | Add a work-order model linked to existing entities, with assignment, priority, SLA, review and event history. Generate tasks from existing transitions incrementally. | New work-order queue/detail; role/warehouse filters; assignment and completion actions. | CRUD/transition/assignment/count APIs and generation hooks. | Work order, assignment and event/history tables. | P0 | XL |
| 5. Inventory | Separate pallet-label, SKU stock and cross-dock/load views; dense filters, lifecycle counts, suggested vs actual locations and history. | **PARTIAL:** strong lot/location ledger with aging, quantities, allocation state and controlled transactions, but no SKU/product layer, pallet labels, cycle count or cross-dock control-tower view. | Operational inventory integrity is good, while identity/granularity and alternate views are limited. | Extend the lot ledger with SKU/item and pallet/license-plate children, then add view presets and cycle-count workflow. | SKU, pallet and cross-dock views; label/scan and count screens. | Item/pallet queries, label generation and count reconciliation services. | Product/SKU, pallet/LPN, lot-item and cycle-count tables. | P1 | XL |
| 6. Container Tracking | Container milestones span ETA, warehouse receipt, yard/load, pickup, delivery and POD, with exception visibility and cross-references. | **PARTIAL:** imported container records include ETA/delivery/warehouse timestamps and derived dispatch intelligence; detail links to outbound tasks. | Mostly import/read-only; no event timeline, ownership, manual correction, carrier feed adapter, pickup/delivery/POD completion or alert rules. | Convert the current record into an append-only milestone/event workflow and retain the current derived priority query. | Timeline, edit/correct action, exception badges and saved filters. | Event ingestion/update APIs, alert evaluation and adapter boundary. | Container event, source and alert tables; optional normalized carrier/port fields. | P1 | L |
| 7. Picking | EasyFreight evidence is indirect: picking is treated as work-order/task execution derived from outbound operations. | **PARTIAL:** generates allocation snapshots, supports multiple lists, history/list pages, XLSX and completion quantities. | No assignee/team queue behavior beyond a field, no wave/batch picking, scan verification, per-line status, shortage reason or inventory completion coupling. | Evolve picking lists into executable tasks with line-level state, assignment, location verification and exception handling. | Task detail, mobile/scan-friendly flow, shortage/exception modal and progress. | Line transition, assignment, scan/confirm and exception APIs. | Picking line status/events, assignments and scan records. | P0 | L |
| 8. BOL / POD | Central WHS Alert/BOL page has status tabs/counts, appointments, carrier, POD request/upload/status, export and exception visibility. | **PARTIAL:** BOL header/items are snapshotted from one outbound and downloadable as PDF/XLSX. | No grouped BOL, status actions, POD entity/upload/request, document versions, signatures, delivery proof or alert/count APIs. | Add a document service and POD lifecycle first; then support grouped BOLs through the Load aggregate. | BOL detail drawer, POD request/upload/view, status tabs and document history. | Document metadata/storage abstraction, POD transitions, grouped BOL validation and counts. | Document, POD request/status/version and BOL-group association tables. | P0 | L |
| 9. Unified Search | Recurrent multi-reference filters cover Load/BOL/CNTR/MBL/OB/file/customer/receiver references across operational pages. | **MISSING:** each module has local `q` filters; no global search endpoint, top-bar search or normalized reference index. | Operators must know the owning module; identifiers can be missed across entities. | Build a permission-aware federated search first, then optionally maintain a normalized reference index once Load identities stabilize. | Global top-bar search with grouped results and deep links. | Search aggregation endpoint, ranking and permission filtering. | Phase 1 can use existing indexes; phase 2 adds normalized search/reference index. | P0 | M |
| 10. Exception / Trouble Shoot | Dedicated troubleshoot queue links status counts, CNTR, loads, operator, warehouse alert, revision, description, documents, chat/activity. | **PARTIAL:** outbound has exception/resolve state and reason; dispatch readiness can be BLOCKED. No cross-module case queue. | Exceptions are embedded in one order and lack owner, SLA, category, comments, attachments, escalation and resolution evidence. | Introduce a generic exception case linked to any DLX entity; migrate outbound exception behavior behind it while preserving current endpoints initially. | Exception center, entity-side panels, owner/SLA filters and activity feed. | Case lifecycle, comments, attachments, count and escalation APIs. | Exception case, entity link, activity/comment and attachment tables. | P0 | L |
| 11. RBAC | Current-account menu visibility is observed; role/menu/button plus warehouse/customer scopes are recommended, while EasyFreight enforcement/schema remains unknown. | **PARTIAL:** six enum roles; admin, warehouse-write and outbound-write dependencies; authenticated reads; frontend renders the same menu/actions for all users. | Coarse hard-coded roles, no permissions, scopes, policy audit, user management UI or frontend capability contract. | Add explicit permissions and warehouse/customer scopes; return effective capabilities from `/users/me`; hide/disable navigation and actions accordingly. | Role-aware menu/actions and admin user-role-scope screens. | Central permission dependency/policy service and effective-capability endpoint. | Role/permission, user-role, role-permission, warehouse/customer scope tables. | P0 | L |
| 12. KPI | Dashboard exposes load, transit, warehouse, carrier, work-order, received, pending shipout and pending POD analyses; KPI page scores operators/files. | **MISSING:** no dashboard, metric API, ownership model or KPI event definitions. Dispatch priority is operational intelligence but not historical KPI. | No operational overview, throughput/backlog/SLA metrics or accountable owner data. | Start with auditable operational KPIs derived from existing timestamps: inbound backlog, inventory aging, allocation readiness, pending picks, shipout and POD. | Role-aware dashboard with drill-through cards and trend charts. | Aggregation endpoints and metric definitions; avoid a data warehouse initially. | Add ownership/event timestamps where absent; optional daily snapshots later. | P1 | L |
| 13. Customer | Customers are cross-cutting filters/references and quote scopes. | **PARTIAL:** customer master model and list/create APIs; referenced by inbound, inventory, FBA, outbound and BOL. | No customer page, edit/deactivate workflow, addresses, contacts, external references, service rules or user scope. | Add customer master UI/API lifecycle and operational profile before pricing/accounting features. | Customer list/detail, contacts/addresses and linked activity. | Update/deactivate/detail APIs and referential validation. | Customer address/contact/reference and scope tables. | P1 | M |
| 14. Carrier / Vendor | Vendor management includes contacts, terms, credit, claims, portal state and shipment summary; rate lanes support mode, tiers and effective dates. | **PARTIAL:** carrier model contains code/name/SCAC/contact and list/create APIs; it is linked to FBA, outbound and BOL. | No UI/update/deactivation policy beyond create, vendor distinction, rate cards, lanes, capacity, insurance, terms or performance. | Extend Carrier into a party/vendor profile without breaking current FKs; add lane rate cards only after master governance. | Carrier/vendor management and rate-card screens. | Lifecycle, rate lookup and performance summary APIs. | Party profile, contacts, compliance, lane and tier-rate tables. | P1 | L |
| 15. Accounting integration points | Loads/service orders feed AR/AP invoices, bills, payments, statements, quotes and profit views. | **MISSING:** no accounting entities or APIs; operational records do retain quantities, customer/carrier and references useful for future charge events. | No explicit chargeable event, service order, uninvoiced state, export contract or reconciliation key. | Do not build a full ledger first. Add immutable chargeable-event and service-order integration boundaries tied to Load/work orders, then export/webhook adapters to the chosen accounting system. | Unbilled service queue, integration status and reconciliation view. | Charge-event service, idempotent outbound adapter, mapping and retry APIs. | Service order, charge event, integration run/error and external ID tables. | P1 | XL |

## 4. Cross-cutting findings

### Strengths to preserve

1. Inventory/FBA/Outbound quantity changes use row locks, validation, transactions and audit records rather than UI-calculated balances.
2. The import platform is unusually mature for the current product stage: streaming reads, profiles, validation, provenance, idempotency controls and reconciliation are already present.
3. Dispatch urgency is separated correctly from inventory aging and is business-timezone aware, including DST boundary tests.
4. Workbench interaction is already efficient: server filters, URL-selected records, batch actions, selected export and persistent split layouts.
5. Authentication has hashed passwords, token separation, refresh rotation behavior and automatic single retry.

### Architectural cautions

- Add Load and Work Order as linking/orchestration concepts; do not collapse Inbound, Inventory, FBA and Outbound into one replacement model.
- Keep quantity mutation in the existing inventory allocation services. New task/load pages should orchestrate those services, not duplicate balance logic.
- Use append-only events for milestones, exceptions and documents where history matters.
- Treat EasyFreight's 48-column screens as evidence of information needs, not a UI template. DLX should use view presets and configurable columns.
- Resolve permission scope at the backend. Frontend hiding alone is not authorization.

## 5. Overall assessment

**Current DLX maturity: 6.5/10 — operational-core beta.** Inbound, lot inventory, FBA, outbound allocation/dispatch, controlled imports and dispatch intelligence form a credible tested core. The product is not yet an end-to-end warehouse/freight operations platform because it lacks the shared Load and Work Order layers, full picking/POD execution, cross-module exception/search, scoped RBAC, analytics and accounting handoff.

**Biggest five gaps:**

1. Canonical Load Management/control tower.
2. Warehouse Work Order and executable picking task lifecycle.
3. BOL/POD document and delivery-proof workflow.
4. Unified exception/troubleshoot center plus global reference search.
5. Scoped RBAC and the KPI/accounting integration foundation.

**Features DLX already does better (relative to behavior evidenced in the supplied EasyFreight reports):**

- Explicit, tested FBA allocation/release and Outbound inventory integrity.
- Traceable, profile-driven Excel import with preview, validation, errors, reconciliation and idempotency controls.
- Business-timezone/DST-aware dispatch priority and conservative readiness calculation.
- Purpose-built FBA and Outbound workbenches with selected export and persistent splitters.
- Clearly evidenced access/refresh-token behavior and backend role gates; the EasyFreight mechanism was unknown in the supplied analysis.

These are evidence comparisons, not claims that EasyFreight lacks unobserved functionality.

**Recommended next phase:** **PHASE 10 — Operational Orchestration Foundation**, centered on canonical Load identity, global reference search, generic exceptions and scoped RBAC, followed immediately by warehouse work orders and POD execution.

**Recommended first task:** **Global Multi-Reference Search (read-only MVP)**. It delivers immediate operator value, exposes reference/data-quality issues needed to design Load identity safely, has no quantity-mutation risk, and becomes the navigation spine for the later control tower.
