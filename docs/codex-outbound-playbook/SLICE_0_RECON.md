# Outbound EF Parity — Slice 0 Reconciliation

## Scope and baseline

- Baseline branch: `feature/java-api-parity`
- Baseline commit: `d79d47d0f7c8ca506c4ab6c4a2eea3a54acb1ca2`
- Parent branch created from the baseline: `feature/outbound-ef-parity`
- Slice branch created from the parent: `feature/outbound-ef-parity-slice-0`
- This slice is reconciliation and documentation only. It makes no backend, frontend, migration, database, browser, or EasyFreight changes.
- The Slice 1–5 prompt files were not read. The boundaries below use the approved functional allocation supplied by the human reviewer; each future slice prompt remains authoritative within that allocation.

## Current implementation map

### Entry point and state

- `frontend/src/App.tsx:9,43` lazy-loads `OutboundDispatchWorkbenchPage` at `/outbound/dispatch`.
- `frontend/src/pages/OutboundDispatchWorkbenchPage.tsx:92-106` owns modal state, right-panel state, and selected outbound IDs. The selected detail is resolved from `selected_ob` or the first selected ID (`:137-150`).
- List/detail refresh invalidates both queries (`frontend/src/pages/OutboundDispatchWorkbenchPage.tsx:165-168`).
- The page is currently covered by `// @ts-nocheck`; future work should not treat that as evidence that request/response shapes are correct.

### Backend workbench contract

- `backend/app/api/v1/endpoints/outbound.py:31-33` exposes the workbench list with the exact nine supported query fields.
- `backend/app/services/outbound_workbench.py:19-33` applies search, filters, sorting, pagination, readiness, blocking reasons, and allowed actions.
- `backend/app/services/outbound_workbench.py:34-44` assembles the detail response, including allocations, picking, BOLs, workflow, remaining quantity, and allowed actions.

## Confirmed API reconciliation

### Filters

The supported workbench query contract is exactly:

1. `q`
2. `status`
3. `ob_type`
4. `warehouse_id`
5. `carrier_id`
6. `page`
7. `per_page`
8. `sort_by`
9. `sort_order`

Current frontend behavior is partial but contract-compatible:

- `frontend/src/pages/OutboundDispatchWorkbenchPage.tsx:108-135` sends the nine fields.
- Additional UI search fields (`id`, `bol_no`, `container_number`, `delivery_location`, `transfer_address`, `reference_search`, `del_ref`, and `agent_code`) are folded by precedence into the single `q` value rather than sent as unsupported API parameters.
- `frontend/src/types/outbound.ts:3` still exposes the legacy UI fields alongside the supported contract. Slice 2 should keep the API boundary explicit so these fields cannot accidentally leak into the request.
- Backend `q` search covers outbound/reference/FC/DEL/FBA/ST/PO/container data (`backend/app/services/outbound_workbench.py:19-33`).
- Filtered export is narrower than the workbench list: `backend/app/api/v1/endpoints/outbound.py:24-28` accepts only `q`, `status`, `ob_type`, and `warehouse_id`. The UI must not imply that carrier, sort, or pagination alter the filtered-export payload unless the backend contract changes in an separately authorized task.

### Batch lifecycle operations

The authoritative endpoint is:

`POST /api/v1/outbounds/workbench/batch`

The authoritative response contract is:

- `results[].id`
- `results[].status`
- `results[].reason`
- top-level `successful`
- top-level `failed`

Fields such as `outbound_id`, `succeeded`, or `total` are not part of the current response and must not be assumed.

`backend/app/api/v1/endpoints/outbound.py:57-71` performs the per-ID server-side execution and aggregates the real result contract. A multi-selected lifecycle action must send exactly one batch request. The frontend must not issue a loop of single-outbound lifecycle requests.

Current bulk lifecycle implementation: **ABSENT**.

- `frontend/src/api/outbound.ts:13-20` defines only single-ID lifecycle helpers; it has no workbench batch helper.
- `frontend/src/pages/OutboundDispatchWorkbenchPage.tsx:169-185` maps lifecycle operations to single-ID functions.
- `frontend/src/components/outbound-workbench/DispatchCommandBar.tsx` receives `selectedCount`, but its lifecycle callbacks are invoked once and the page applies them only to `selected.id` (`frontend/src/pages/OutboundDispatchWorkbenchPage.tsx:547-589`).
- Exact evidence: `frontend/src/api/outbound.ts:15-20` exports only the single-record functions `confirmOutbound`, `dispatchOutbound`, `completeOutbound`, `cancelOutbound`, `exceptionOutbound`, and `resolveOutbound`; it has no batch helper. `frontend/src/pages/OutboundDispatchWorkbenchPage.tsx:169-185` maps its `action` mutation to those single-record functions, while `:577-586` and `:739-772` pass only `selected.id`. `frontend/src/components/outbound-workbench/DispatchCommandBar.tsx:11,30-38` receives a count but exposes ordinary callbacks rather than an ID collection. There is also no loop over `selectedIds` for lifecycle requests. Therefore the required multi-select lifecycle implementation is absent, not unknown and not looped single calls. Selected export and Create Load are separate multi-record endpoints and are not lifecycle batch implementations.

### Dispatch readiness and blocking reasons

- `backend/app/api/v1/endpoints/outbound.py:72-75` exposes `GET /outbounds/{id}/dispatch-readiness`.
- `backend/app/schemas/dispatch_readiness.py:15-20` defines `READY` / `NOT_READY`, checks, `blocking_reasons`, `blocking_codes`, and `error_code`.
- `backend/app/services/dispatch_readiness.py:26-103` calculates readiness. Loaded outbounds are rejected with `Must dispatch through Load`; allocation, picking, BOL, carrier, confirmation, and unresolved-exception checks can block dispatch.
- `backend/app/services/dispatch_readiness.py:106-110` returns the complete readiness object in a 409 dispatch rejection. The outbound dispatch service calls this guard before transition (`backend/app/services/outbound.py:89-107`).
- `frontend/src/api/outbound.ts:3-8` defines the readiness response and helper, but the page does not call the dedicated helper.
- The list row carries readiness/allowed-action data from the backend, and `frontend/src/pages/OutboundDispatchWorkbenchPage.tsx:299-303` passes only the status to `DispatchIndicators`.
- `frontend/src/components/DispatchIndicators.tsx:9-11` shows a generic status tooltip and does not render actual `blocking_reasons`. Its displayed status vocabulary also includes `BLOCKED`, `PARTIAL`, and `COMPLETED`, while the readiness endpoint uses `READY` and `NOT_READY`.
- `frontend/src/pages/OutboundDispatchWorkbenchPage.tsx:169-185` reduces lifecycle errors to the generic message `Operation rejected`, losing server-provided blocking reasons.

Dispatch readiness wiring is therefore **PARTIAL**. Slice 1 must preserve and surface the actual server reasons both before dispatch and after a rejected batch item; a generic synthesized blocking reason is a review-gate failure.

## Functional inventory and gaps

| Area | Current state | Evidence and confirmed gap |
| --- | --- | --- |
| Create outbound | Present; auto-selection absent | Create closes and refreshes (`OutboundDispatchWorkbenchPage.tsx:186-194`) but does not select/open the returned outbound. |
| Row/multi-select | Present | IDs are maintained by the page and table (`:92-106`, `:691-694`), but lifecycle actions ignore the selected set. Cross-page selection is **DEFERRED / FUTURE_WORK**. |
| Allocation | Present; partial feedback | Allocation submits remaining/available quantities and refreshes (`:433-453`), but the raw promise has no pending/error handling. |
| Release allocation | Present; partial feedback | Release refreshes (`:380-390`), but likewise has no pending/error handling. |
| Filtered export | Present | `frontend/src/api/outbound.ts:21`; the backend accepts a narrower filter set than the list endpoint. |
| Selected export | Present | `frontend/src/api/outbound.ts:22` and page `:605-614` send the selected IDs. |
| Create Load | Present | Page `:195-216,615-621` navigates after creating from selected IDs. Backend validation is authoritative (`backend/app/services/load.py:21-38`). Client same-warehouse checks only inspect rows available on the current page and must not be treated as sufficient validation. Post-Create-Load navigation changes are **DEFERRED / FUTURE_WORK**. |
| Picking | Present for one selected outbound | Page `:464-480` uses `frontend/src/api/pickingBol.ts`; no multi-select batch wiring exists. |
| BOL | Present for one selected outbound | Page `:464-480` uses `frontend/src/api/pickingBol.ts`; no multi-select batch wiring exists. |
| Confirm/dispatch/complete/cancel | Single selected only | Page `:169-185,547-589,734-776`; required batch behavior is absent. |
| Exception action | Incomplete/dead; deferred | The page imports `exceptionOutbound` and opens `exceptionOpen`, but the operation map omits `exception` and no exception modal/panel is rendered. Exception wiring is **DEFERRED / FUTURE_WORK**. |
| Delete command | Misnamed behavior; deferred | The command bar's delete callback currently performs a single-outbound cancel, not deletion and not a batch operation. Delete/cancel semantics are **DEFERRED / FUTURE_WORK**. |

## Confirmed discrepancies that must block premature parity claims

1. Multi-select lifecycle operations are absent; selected count does not make the current single-row callback a bulk implementation.
2. No frontend helper calls `/api/v1/outbounds/workbench/batch`.
3. The real batch response fields are not parsed or displayed.
4. Dispatch blocking reasons are available from the backend but are not shown in the workbench.
5. Lifecycle failures are collapsed into a generic error.
6. Create success does not select the new outbound.
7. Allocation/release refresh on success but lack explicit pending/error feedback.
8. Exception UI wiring and Delete/cancel semantics are unresolved but are **DEFERRED / FUTURE_WORK**, not assigned to Slices 1–5.
9. Filtered export supports fewer filter fields than the list endpoint.
10. Create Load's client validation is page-local; backend validation must remain authoritative.

## Approved Slice 1–5 boundaries

### Slice 1 — Workbench batch + dispatch readiness

- Connect dispatch readiness.
- Surface `blocking_reasons`.
- Implement/use one `POST /api/v1/outbounds/workbench/batch` for approved multi-select lifecycle actions.
- Use the actual response: `results[{id,status,reason}]`, `successful`, and `failed`.
- Apply functional three-region naming/organization only where already approved.

### Slice 2 — Create auto-selection + allocation/release refresh

- Newly created outbound automatically becomes selected.
- Middle/right regions follow selection.
- Allocation refreshes detail/source.
- Release refreshes detail/source.
- Prevent stale selection/detail state.

### Slice 3 — Filters + columns using existing fields only

Existing backend fields:

- `q`
- `status`
- `ob_type`
- `warehouse_id`
- `carrier_id`
- `page`
- `per_page`
- `sort_by`
- `sort_order`

Boundary rules:

- No invented dedicated filter parameters.
- Extra search inputs continue through `q` where applicable.
- No empty Team/Notify columns.
- Only real existing data-backed columns.

### Slice 4 — Export + Create Load + batch Picking/BOL

- Filtered export.
- Selected export.
- Create Load.
- Batch Picking.
- Batch BOL.
- No BOL generator redesign.

### Slice 5 — Gap / changelog only

- Update gap report.
- Update changelog.
- Document implemented/deferred items.
- Zero new functionality.

Slice 5 must not contain Picking/BOL implementation, exception wiring, Delete/cancel changes, action cleanup, API wiring, new buttons, functional fixes, or UI polish.

## Approved gap-to-slice mapping

| GAP | ASSIGNED_SLICE |
| --- | --- |
| Dispatch readiness / `blocking_reasons` | Slice 1 |
| Workbench batch lifecycle | Slice 1 |
| Create auto-selection | Slice 2 |
| Allocation/release refresh | Slice 2 |
| Filters/columns | Slice 3 |
| Filtered export | Slice 4 |
| Selected export | Slice 4 |
| Create Load | Slice 4 |
| Batch Picking/BOL | Slice 4 |
| Gap/changelog closeout | Slice 5 |
| Exception wiring | DEFERRED |
| Delete/cancel semantics | DEFERRED |
| Cross-page selection | DEFERRED |
| Post-Create-Load navigation | DEFERRED |

## Unresolved questions for human review

1. Which lifecycle operations should be exposed as multi-select commands in Slice 1: all backend batch operations, or only the operations currently present in the command bar?
2. Should partial batch success keep failed IDs selected, clear successful IDs, or preserve the full selection?
3. Should readiness details be fetched on selection, on dispatch intent, or both, given that the list already includes readiness fields?
4. **DEFERRED / FUTURE_WORK:** Is the command bar's `Delete` label intended to mean cancellation, or should it be removed because no delete endpoint exists?
5. **DEFERRED / FUTURE_WORK:** Should the incomplete exception control open an existing UI component not currently wired here, or be removed until a separately authorized exception UI exists?
6. **DEFERRED / FUTURE_WORK:** For selection across pagination/filter changes, should hidden IDs remain selected or be cleared?
7. Should filtered export intentionally ignore carrier and sort state, or does that backend endpoint require a separately scoped contract change?
8. **DEFERRED / FUTURE_WORK:** After Create Load, is navigation to `/loads?selected=...` the intended parity destination, or should the newly created load ID be used if returned?

## Slice 0 review gate

- Batch-contract reconciliation: **PASS**
- Filter-contract reconciliation: **PASS**
- Dispatch-blocking reconciliation: **PASS**
- Current bulk classification: **ABSENT**
- Dispatch readiness wiring: **PARTIAL**
- Create auto-selection: **ABSENT**
- Allocation refresh: **PARTIAL**
- Export actions: **PRESENT**
- Create Load action: **PRESENT**
- Picking/BOL actions: **PRESENT FOR ONE SELECTED OUTBOUND**
- Proposed implementation scope is frontend-only and split into reviewable functional slices: **PASS**
- Ready for human review of the reconciliation report: **YES**
- Ready to start Slice 1 without human approval: **NO**

## Human verification commands

Run only after reviewing this report:

```powershell
cd "C:\Users\XL\dlx-yuki-wms\frontend"
npm run build
cd "C:\Users\XL\dlx-yuki-wms"
git diff --check
git status --short
git diff --name-status
git diff --stat
```

Slice 0 does not run the frontend build because its only authorized change is this documentation report. No Slice 1–5 work is started here.
