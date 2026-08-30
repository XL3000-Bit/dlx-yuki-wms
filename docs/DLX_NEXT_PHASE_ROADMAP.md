# DLX Yuki WMS — Next Phase Roadmap

**Proposed phase:** PHASE 10 — Operational Orchestration Foundation  
**Basis:** current-source audit plus EasyFreight → DLX gap analysis dated 2026-08-29.

## Phase outcome

Connect the already working Inbound → Inventory → FBA/Outbound → Picking/BOL core through shared identity, tasks, exceptions, documents and permissions. This phase should enhance existing modules rather than replace their tested allocation and transaction logic.

## Delivery sequence

1. **Foundation:** global search, permission model and canonical reference rules.
2. **Orchestration:** Load control tower and generic exception cases.
3. **Execution:** work orders, line-level picking and POD/document lifecycle.
4. **Visibility/integration:** KPI cards, master-data governance and charge-event handoff.

## NEXT 10 DEVELOPMENT TASKS

### 1. Global Multi-Reference Search MVP

| Field | Plan |
|---|---|
| Task Name | Global Multi-Reference Search MVP |
| Why | Operators currently search each module separately. A read-only federated search gives immediate value and reveals duplicate/missing references before the Load model is finalized. |
| Affected Files/Modules | New search endpoint/service/schema; `AppLayout`; existing Inbound, Container Tracking, Inventory, FBA, Outbound and BOL query/index paths. |
| Frontend | Add top-bar search, grouped result panel, keyboard navigation and deep links to selected records. |
| Backend | Federate exact/prefix matches for CNTR, MBL, HBL, inbound, lot, FBA/ST/PO, OB and BOL; enforce current-user visibility. |
| Database | Reuse current indexes first; add only missing normalized/case-insensitive indexes after query-plan measurement. |
| Tests | Ranking, duplicate references, empty input, permission filtering, deep-link shape and query-count/performance tests. |
| Priority | P0 |
| Complexity | M |
| Dependencies | Existing module APIs and authentication; no new domain model required. |

### 2. Explicit RBAC and Warehouse/Customer Scopes

| Field | Plan |
|---|---|
| Task Name | Explicit RBAC and Warehouse/Customer Scopes |
| Why | Current enum roles protect broad writes but cannot enforce warehouse/customer boundaries or drive menus/buttons safely. |
| Affected Files/Modules | `users`, API dependencies, auth schemas, all list/write services, `AppLayout`, action-heavy pages. |
| Frontend | Capability-aware navigation/actions and an admin user-role-scope screen. |
| Backend | Permission policy service, scoped query helpers, effective capabilities in `/users/me`, migration compatibility for existing roles. |
| Database | Roles, permissions, mappings, user warehouse scopes and user customer scopes. |
| Tests | Endpoint permission matrix, cross-warehouse/customer denial, admin migration compatibility and frontend capability rendering. |
| Priority | P0 |
| Complexity | L |
| Dependencies | Should start before new Load/Work Order write endpoints. |

### 3. Canonical Load and Reference-Link Model

| Field | Plan |
|---|---|
| Task Name | Canonical Load and Reference-Link Model |
| Why | CNTR/MBL/BOL/customer references are fragmented across modules; a stable aggregate is required for a control tower, grouped documents and accounting handoff. |
| Affected Files/Modules | New load model/schema/service/API; import reconciliation; links to container, inbound, FBA, outbound and BOL. |
| Frontend | Initially none beyond search showing proposed/linked Load identity; admin reconciliation UI may follow. |
| Backend | Deterministic link rules, duplicate/conflict detection, idempotent backfill and read-only aggregate detail. |
| Database | `loads`, normalized `load_references`, and typed entity associations; retain existing entity tables/FKs. |
| Tests | Duplicate identifiers, split/merge safeguards, import idempotency, association integrity and rollback. |
| Priority | P0 |
| Complexity | XL |
| Dependencies | Task 1 data findings; Task 2 scope rules. |

### 4. Load Control Tower

| Field | Plan |
|---|---|
| Task Name | Load Control Tower |
| Why | Users need one operational view of container, warehouse, inventory, outbound, BOL, carrier, milestones and readiness. |
| Affected Files/Modules | New Load page/API; existing container dispatch aggregates, outbound workbench, BOL and inventory. |
| Frontend | Lifecycle tabs/counts, compact filters, configurable view presets, summary and linked detail panels. |
| Backend | Server pagination/filter/sort/counts and an aggregate detail endpoint with bounded query counts. |
| Database | Load associations from Task 3; user column/view preferences if included. |
| Tests | Status counts, filter parity, authorization, N+1 regression and deep-link navigation. |
| Priority | P0 |
| Complexity | L |
| Dependencies | Tasks 2 and 3. |

### 5. Unified Exception / Trouble Shoot Center

| Field | Plan |
|---|---|
| Task Name | Unified Exception / Trouble Shoot Center |
| Why | Outbound exceptions exist, but cross-module issues have no owner, SLA, activity trail or shared queue. |
| Affected Files/Modules | New exception model/API/page; Outbound exception service; Container, Import, Picking and BOL integrations. |
| Frontend | Queue with status counts, entity links, owner/SLA/category filters and activity/comments panel. |
| Backend | Generic entity-linked cases, transition rules, assignment/escalation and compatibility wrapper for current outbound endpoints. |
| Database | Exception case, entity link, activity/comment and attachment metadata tables. |
| Tests | State machine, ownership/scope, SLA calculation, outbound compatibility and audit history. |
| Priority | P0 |
| Complexity | L |
| Dependencies | Task 2; benefits from Task 3 but can support typed entity links first. |

### 6. Warehouse Work Order Foundation

| Field | Plan |
|---|---|
| Task Name | Warehouse Work Order Foundation |
| Why | Inbound, put-away, move, pick and load actions need a common assignable execution queue and lifecycle. |
| Affected Files/Modules | New work-order domain; Inbound, Inventory, Picking and Outbound transition hooks. |
| Frontend | Work-order list/detail, type/status/priority tabs, assignment, start/complete/review actions. |
| Backend | Number generation, state machine, assignment, counts and incremental task-generation hooks. |
| Database | Work orders, entity links, assignments and event history. |
| Tests | Transition matrix, idempotent generation, assignment/scope, counts and rollback around linked domain actions. |
| Priority | P0 |
| Complexity | XL |
| Dependencies | Tasks 2 and 3; Task 5 for exception linkage. |

### 7. Picking Execution V2

| Field | Plan |
|---|---|
| Task Name | Picking Execution V2 |
| Why | Current picking snapshots and completion are useful but do not support line progress, assignment, scan/location verification or shortages. |
| Affected Files/Modules | Picking models/services/endpoints/page; Inventory allocation checks; Work Orders. |
| Frontend | Mobile-friendly task view, scan/manual confirmation, progress, shortage reason and exception creation. |
| Backend | Per-line transitions, concurrency controls, assignment and exception integration; preserve current snapshot generation. |
| Database | Picking line status/events, scan records and assignment/work-order link. |
| Tests | Concurrent picks, over-pick prevention, partial/short completion, scan mismatch, retry/idempotency and audit. |
| Priority | P0 |
| Complexity | L |
| Dependencies | Tasks 5 and 6. |

### 8. BOL / POD Document Workflow

| Field | Plan |
|---|---|
| Task Name | BOL / POD Document Workflow |
| Why | DLX can generate BOL files but cannot request, upload, version, track or resolve POD delivery proof. |
| Affected Files/Modules | BOL service/page, Outbound/Load detail, new document storage abstraction and exception hooks. |
| Frontend | BOL detail, status tabs/counts, POD request/upload/view, document history and missing-POD alert. |
| Backend | File metadata/storage interface, POD lifecycle, secure download, versioning and eventual grouped-BOL support. |
| Database | Documents, versions, POD requests/status/events and Load/BOL associations. |
| Tests | File authorization, content/size validation, version history, POD transitions, missing-address cases and storage failures. |
| Priority | P0 |
| Complexity | L |
| Dependencies | Tasks 2, 3 and 5; external object-storage choice can be adapter-based. |

### 9. Customer and Carrier/Vendor Master Governance

| Field | Plan |
|---|---|
| Task Name | Customer and Carrier/Vendor Master Governance |
| Why | Existing models/APIs are adequate references but not manageable operational master data; future scopes, rates and accounting need governed identities. |
| Affected Files/Modules | Master data endpoints/schemas/models; new customer and carrier/vendor pages; FBA/Outbound selectors. |
| Frontend | Searchable list/detail/edit/deactivate, contacts/addresses, duplicate warnings and linked activity. |
| Backend | Update/deactivate/merge safeguards, normalized identifiers and usage summaries. |
| Database | Contacts, addresses, external references, vendor profile/compliance; defer rate tables to a follow-up if needed. |
| Tests | Uniqueness, inactive-reference rules, merge protection, scope enforcement and regression for existing selectors/imports. |
| Priority | P1 |
| Complexity | M |
| Dependencies | Task 2; coordinate normalized references with Task 3. |

### 10. Operational KPI and Charge-Event Integration Foundation

| Field | Plan |
|---|---|
| Task Name | Operational KPI and Charge-Event Integration Foundation |
| Why | Management lacks backlog/SLA visibility, while future accounting needs an idempotent boundary rather than direct coupling to warehouse transactions. |
| Affected Files/Modules | New dashboard metrics, Load/Work Order/POD events, service-order/charge-event module and integration-run monitoring. |
| Frontend | KPI cards with drill-through plus unbilled/integration-status queue. |
| Backend | Defined metric queries, immutable charge-event producer, mapping/export adapter, retry and reconciliation endpoints. |
| Database | Missing owner/event timestamps, optional daily KPI snapshots, service orders, charge events and integration run/error records. |
| Tests | Metric definition fixtures, timezone boundaries, idempotent charge emission, adapter retry and reconciliation. |
| Priority | P1 |
| Complexity | XL |
| Dependencies | Tasks 3, 6 and 8; accounting target contract must be agreed before adapter implementation. |

## Acceptance gates for PHASE 10

- Existing 74 backend tests continue to pass; new migrations upgrade from the current head and have downgrade coverage appropriate to project policy.
- Every new list endpoint enforces warehouse/customer scope, paginates server-side and has a bounded-query/N+1 test.
- No new workflow writes inventory quantities outside the existing locked transaction services.
- Search, Load, Work Order, Exception and Document entities have deterministic deep links and audit/event histories.
- Picking and POD happy paths plus partial, concurrent, unauthorized and retry paths are tested.
- Frontend unit/component testing is introduced before the new cross-module workflows become large; TypeScript build alone is not the final acceptance gate.

## Recommended release slices

| Slice | Tasks | Deliverable |
|---|---|---|
| 10A — Find and secure | 1–2 | Global navigation/search and scoped authorization foundation. |
| 10B — Connect operations | 3–5 | Canonical Load, control tower and exception center. |
| 10C — Execute and prove | 6–8 | Work orders, picking V2 and BOL/POD document closure. |
| 10D — Govern and measure | 9–10 | Master governance, operational KPIs and accounting integration boundary. |

## First implementation recommendation

Start with **Task 1: Global Multi-Reference Search MVP**. It is read-only, relatively contained and immediately useful. More importantly, its test data and collision findings will reduce the design risk of Task 3's canonical Load identity. In parallel planning (not coding), define the permission matrix required by Task 2 so that every later endpoint is scoped from its first release.
