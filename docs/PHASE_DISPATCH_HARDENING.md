# Dispatch Hardening (11.3-lite)

> 历史阶段说明：当前单订单派发入口已阻断并要求通过派车单事务入口。不可用下文的早期 READY 条件作为实际派发授权；参见 [2026-10-05 派发闭环验收记录](DISPATCH_CLOSURE_ACCEPTANCE_2026-10-05.md)。

> 同日后续：真实持久化证据已接入事务内校验，见 [证据与浏览器验收](DISPATCH_EVIDENCE_ACCEPTANCE_2026-10-05.md)。仅有 BOL 或只读预检 PASS 不能授权派发；未确认生产策略继续阻断。

This slice adds a dispatch-readiness gate without changing picking, inventory, load, POD, scan, or staging behavior.

An outbound is `READY` only when it is `CONFIRMED`, has a positive inventory allocation, has picked at least the allocated pallet quantity, has a generated non-empty BOL, has a carrier, and has no `OPEN` or `INVESTIGATING` operational exception. Any failed check makes it `BLOCKED`.

`GET /api/v1/outbounds/{id}/dispatch-readiness` exposes the checks and blocking reasons. Individual and workbench batch dispatch actions use the same server-side gate; blocked records return HTTP 409 and retain their prior status. Existing outbound write permission and warehouse visibility rules remain in force.

The outbound workbench disables individual dispatch while blocked and displays the failed checks with links to existing Picking, BOL, and Trouble Shoot routes where applicable.

This slice intentionally does not require a Load, pickup schedule, POD, ScanSession, ScanEvent, staging, or load verification. It creates no migration and does not alter inventory deduction or completion semantics.
