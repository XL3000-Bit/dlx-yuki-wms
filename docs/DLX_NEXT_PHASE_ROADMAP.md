# DLX Yuki WMS — Next Phase Roadmap

> 最新检查点（2026-10-07 15:51 PDT）：[冻结候选完整回归](evidence/dispatch-candidate-final-20261007-1548/README.md)。全项目前端严格类型检查 0 错误、构建通过；完整后端 421 通过 / 1 个 SQLite 行锁场景跳过（独占 PostgreSQL 另验）、只读预检 21、前端 55、PostgreSQL 47 场景、正式页面 E2E 3 测试 / 16 场景通过。两类业务合法计划 v2 使旧审批及关联证据失效，刷新重登保持阻断，重取证据后派发及下游通过。原生文件选择仍未验证，生产规则待批准；mechanism_acceptance_complete=false、production_ready=false。全部本轮资源停止，保留证据及旧未提交成果。

> 历史检查点（2026-10-07 13:42 PDT）：[独占正式页面 E2E](evidence/dispatch-playwright-20261007-134226/README.md) 3 个测试 / 12 场景通过，FBA 与私仓上传后完整链已验证。相关后端 72、前端 53、独占 PostgreSQL 47、E2E 严格类型检查及构建通过；全前端严格语义检查失败 24 错误，完整后端未重跑。原生文件选择仍未验证，整体机制验收未完成，production_ready=false。旧 Chrome 工具未重试，历史总数不计本轮通过。

> 历史路线图：以当前代码和验证为准，不因早期“未完成”重复开发。库存、计划、执行及状态闭环见 [闭环验收](DISPATCH_CLOSURE_ACCEPTANCE_2026-10-05.md)；持久化单据/审批/异常证据与隔离浏览器验收见 [2026-10-05 证据验收](DISPATCH_EVIDENCE_ACCEPTANCE_2026-10-05.md)。生产规则仍未确认、未启用。

> 2026-10-07 历史检查点：[技术收尾与隔离上线演练](DISPATCH_RELEASE_ACCEPTANCE_2026-10-07.md)。本次后端 420 通过/1 跳过、只读预检 21、前端 51、构建通过，隔离 PostgreSQL 47 场景通过（含 SQLite 跳过的部分出库竞争）；浏览器响应 40 断言和恢复/发布演练 16 项通过。原生文件选择、完整当前业务页面验收未完成，整体阶段未结束；TEST_ONLY 不代表生产可用。

> 2026-10-07 历史页面补验追加：[实际页面证据](evidence/dispatch-ui-20261007/README.md)。两类页面完成到缺证据派发阻断；修复核验状态恢复及账号权限缓存，相关后端 23 / 最新前端 7 / 类型与构建通过。原生上传工具阻塞，上传后完整链尚未验证，机制验收整体未结束；上段测试数为此前记录，不能计为本次通过。

**Roadmap date:** 2026-08-31
**Baseline:** PHASE 10 frozen RC plus completed PHASE 11.0 and PHASE 11.1 execution foundations

## Release baseline

```text
PHASE 10
FORMAL RELEASE CANDIDATE
FROZEN

PHASE 11.0
Scan Execution Foundation
COMPLETE

PHASE 11.1
Picking Scan Workflow
COMPLETE
```

PHASE 10's PostgreSQL migration blockers are closed. The 0019/0020 enum lifecycle and 0021 schema alignment were verified with Fresh PostgreSQL, `0012 -> head`, `alembic check`, automated tests, and final manual smoke. `20260830_0020` must not be carried forward as an open roadmap blocker.

PHASE 11.0 established `ScanSession`, immutable `ScanEvent`, the scan workbench, RBAC enforcement, PostgreSQL verification, and a 127-test backend baseline. PHASE 11.1 then added transactional PICK execution, idempotency/concurrency guarantees, and a 135-test backend baseline.

## Current P0

| Order | Milestone | Status | Outcome |
| ---: | --- | --- | --- |
| 1 | PHASE 11.1 — Picking Scan Workflow | COMPLETE | Scan-confirmed picking updates outbound and inventory state transactionally |
| 2 | PHASE 11.2 — Staging / Load Verification | IMPLEMENTED / ISOLATED VERIFIED | Staging quantities and immutable load verification checked by transactional dispatch |
| 3 | PHASE 11.3 — Dispatch Readiness Gate | PARTIAL PAGE VERIFIED / PRODUCTION RULES BLOCKED | Persistent documents, plan approval and exception review; PG and browser test-policy acceptance; production authorization remains disabled |
| 4 | POD Closure Workflow | PENDING | Capture proof, resolve delivery exceptions, and close the outbound lifecycle |

PHASE 11.2 and PHASE 11.3 have isolated implementation evidence. Formal TEST_ONLY page chains now pass through dispatch and downstream details; native file selection and full frontend semantic typecheck remain incomplete. Production still requires per-domain approved rules and controlled rollout acceptance. POD remains outside this task.

## NEXT 10 DEVELOPMENT TASKS

### 1. PHASE 11.1 — Picking Scan Workflow

**Status:** COMPLETE

Delivered transactional PICK behavior, quantity validation, inventory/outbound updates, idempotency, concurrency protection, RBAC, PostgreSQL verification, and regression coverage.

No new PHASE 11.1 feature work is planned. Treat its behavior as the input contract for staging.

### 2. PHASE 11.2 — Staging / Load Verification

**Status:** IMPLEMENTED / ISOLATED VERIFIED (2026-10-07)
**Priority:** P0

Delivered the execution step between picking and dispatch; current isolated tests and browser flows cover:

- scan or otherwise verify staged handling units
- validate outbound, warehouse, quantity, and load association
- prevent cross-warehouse and cross-outbound contamination
- record immutable execution evidence
- make retries idempotent and concurrent attempts safe
- expose actionable mismatch and incomplete-state errors

Do not weaken existing inventory or outbound invariants to achieve parity with an external UI.

The separate EasyFreight parity-capture artifact currently labeled PHASE 11.2 remains a read-only evidence track. Controlled writes stay blocked until a designated safe test environment and fixture are approved. That artifact is not implementation authorization.

### 3. PHASE 11.3 — Dispatch Readiness Gate

**Status:** PARTIAL PAGE VERIFIED / PRODUCTION RULES BLOCKED (2026-10-07)
**Priority:** P0

Implemented one authoritative readiness decision with same-transaction dispatch revalidation that checks:

- required quantities picked and staged
- load verification complete
- unresolved blocking exceptions absent
- warehouse and load identities consistent
- required documents and operational approvals present

Dispatch must fail closed with explicit reasons when a required condition is not met. Repeated dispatch requests must not duplicate inventory, notification, history, or external effects.

Persistent evidence, immutable policy versions, scoped reviews, expiry/revocation and operator pages are implemented. Current isolated verification: 47 PostgreSQL scenarios and 12 formal-page TEST_ONLY scenarios (3 Playwright tests), including FBA/private successful dispatch and downstream details. Native file selection remains unverified; full frontend semantic typecheck has 24 errors. No production policy was enabled. Business decisions remain pending in DISPATCH_RELEASE_PREPARATION_2026-10-05.md; historical screenshots and fixtures are not production-rule authority.

### 4. POD Closure Workflow

**Status:** PENDING
**Priority:** P0

Complete the outbound lifecycle with:

- POD document capture and versioning
- delivery status and receipt metadata
- missing/invalid POD exception path
- linked work-order support where operational follow-up is required
- immutable closure history and permission enforcement

### 5. SKU Master Foundation

**Status:** PENDING
**Priority:** P1

Introduce canonical SKU identity, customer ownership, units of measure, dimensional data, and lifecycle controls. Avoid duplicating SKU definitions inside receipts, inventory rows, or outbound lines.

### 6. LPN / Pallet Identity

**Status:** PENDING
**Priority:** P1

Add durable handling-unit identity with parent/child relationships, warehouse ownership, content traceability, status, and auditable movement history. Reuse scan sessions and events as the execution surface.

### 7. Cycle Count

**Status:** PENDING
**Priority:** P1

Support count plans, blind counting, discrepancy review, approval, adjustment, and audit history. Preserve separation between observed counts and approved inventory mutations.

### 8. Scan-Driven Inventory Execution

**Status:** PENDING
**Priority:** P1

Extend the established scan foundation to receiving, putaway, movement, cycle count, adjustment, and shipment confirmation. Each mutation must be warehouse-scoped, idempotent, auditable, and transactionally consistent.

### 9. Billable Event and Transactional Outbox

**Status:** PENDING
**Priority:** P1

Derive stable billable events from committed WMS operational events and publish them through a transactional outbox. Include deterministic event identity, versioning, retry state, and reconciliation metadata.

### 10. Accounting Adapter and Reconciliation

**Status:** PENDING
**Priority:** P2

Deliver billable events to the selected accounting or ERP system through an adapter with retry, dead-letter visibility, external identifiers, and reconciliation reporting.

The architecture boundary is:

```text
WMS Operational Event
        ↓
Billable Event
        ↓
Transactional Outbox
        ↓
Accounting Adapter
        ↓
External accounting / ERP
```

Do not implement a general ledger, accounts receivable, accounts payable, tax engine, or financial close inside DLX WMS.

## Delivery dependencies

```text
PHASE 10 frozen RC
        ↓
PHASE 11.0 scan foundation (complete)
        ↓
PHASE 11.1 picking (complete)
        ↓
PHASE 11.2 staging / load verification (isolated verified)
        ↓
PHASE 11.3 dispatch readiness (mechanism acceptance incomplete; production rules blocked)
        ↓
POD closure
        ↓
Inventory identity and count expansion
        ↓
Billable events / outbox / accounting adapter
```

## Cross-cutting acceptance gates

Every new execution milestone must preserve:

- warehouse-scoped authorization and data visibility
- immutable and attributable operational history
- idempotency and concurrent-request safety
- PostgreSQL-first migration and lifecycle verification
- fresh-schema and upgrade-path validation
- backend regression coverage and scoped security tests
- frontend build and critical browser workflow smoke
- `git diff --check`
- no Critical or High release issue

## Roadmap constraints

- Do not reopen or silently modify the frozen PHASE 10 RC baseline.
- Do not list scan infrastructure as missing; extend the existing PHASE 11 foundation.
- Do not infer EasyFreight write contracts from read-only observations.
- Do not use production EasyFreight records for parity experiments.
- Do not weaken database constraints to make workflow tests pass.
- Do not rebuild accounting or general-ledger functionality inside the WMS.
