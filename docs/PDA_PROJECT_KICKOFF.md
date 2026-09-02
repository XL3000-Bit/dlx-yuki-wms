# DLX Yuki WMS — PDA Project Kickoff

**Kickoff date:** 2026-09-02
**Initial status:** `PDA_PICK_SLICE = PASS`

## Delivery ledger

| Workstream | Status | Accounting boundary |
| --- | --- | --- |
| PDA PICK slice | `PASS` | `/pda`: location -> lot -> quantity -> confirmation |
| PDA camera scan | `PARTIAL` | UI, native decode injection, fallback, and automated gates complete; real PDA camera not verified in this environment |
| Java v2 readonly | Skeleton green; not routed to production | Separate from PDA; Java `8081` remains a report/master-data shadow |
| FBA allocate/release | Contract green | Separate write-path ledger; no PDA ownership |
| 3PL / other uncommitted work | Retained in parallel; not sealed in this batch | Excluded from this delivery result |

## Product boundary

The first PDA release is an online, mobile-first web client inside the existing React application. Industrial PDA keyboard-wedge scanners are the primary input device. The server remains authoritative for warehouse scope, scan sequence, quantities, idempotency, concurrency, and immutable audit evidence.

The initial route is `/pda`. It deliberately uses a dedicated full-screen shell rather than the desktop WMS navigation.

## Fixed production boundary

| Capability | Current owner/path | Prohibited coupling |
| --- | --- | --- |
| PDA page | React `/pda` standalone entry | Do not insert it into the desktop Outbound three-column workbench |
| Scan and PICK confirmation | Python `/api/v1` | Do not connect PDA writes to Java `/api/v2`; v2 remains readonly |
| Inventory deduction and allocation | Existing Outbound/FBA services | Do not implement a second inventory posting path inside the PDA slice |
| Java `8081` | Report/master-data shadow | PDA must not depend on it yet |

The scan execution service owns session context, PICK sequence validation, append-only scan events, and updates to `PickingListItem.picked_*` / `PickingList.status`. It does **not** mutate `InventoryLot` availability or allocation, `OutboundInventoryAllocation` allocated/completed quantities, or `OutboundOrder.status`. Inventory posting therefore remains outside this PDA slice and inside the established Outbound/FBA write paths.

## First delivery slice — PICK

- Select an authorized warehouse.
- Scan or enter a stable Picking No. to create a PICK session.
- Execute the established `LOCATION -> LOT -> QUANTITY` loop.
- Display server-derived progress, remaining quantity, source context, and recent events.
- Provide visual and optional audio success/error feedback.
- Prevent submissions while the browser reports that it is offline.
- End a complete or partial scan session explicitly.
- Preserve session identity in the URL so a page reload can restore the task.

## Explicitly deferred

- Offline mutation queue and conflict reconciliation.
- Device enrollment, device identity, remote configuration, or MDM.
- Pallet/LPN, SKU, carton, or serial scanning before canonical identifiers exist.
- Receiving, putaway, movement, cycle count, stage, and load-verify PDA flows.

The current offline behavior is UI detection and submission blocking only. There is no local mutation queue or background replay in this slice.

## Camera scanning (2026-09-02)

- **Recognition:** the `/pda` PICK location and lot steps use the browser-native `BarcodeDetector`, with the rear-facing camera preferred through `facingMode: environment`. No scanning package or mobile framework was added. The detector covers common 1D formats plus QR, Data Matrix, and PDF417 when the browser reports support.
- **Protocol:** camera output and manual input both enter `submitScanCode`, then use the unchanged Python `/api/v1` `submitScan` request. Quantity remains manual and continues through the separate `confirmPick` path with the existing `client_operation_id` lifecycle. Camera scanning unmounts and releases its media tracks before the quantity step.
- **Backend:** no backend, request/response field, database, migration, Java, FBA, Outbound inventory/state, STAGE/LOAD, or offline-queue change was made.
- **Permission and compatibility:** permission is requested only after the operator selects **Start scanning**. The browser prefers a rear camera and may select another available camera. Denied permission, missing hardware, insecure context, or lack of `BarcodeDetector` produces a recoverable message and leaves manual input available. Camera access requires an HTTPS secure context in field deployment (localhost remains suitable for development).
- **Duplicate/offline behavior:** a decoded value is submitted at most once while continuously visible, and an accepted value is additionally suppressed for the same PICK step. Moving the code out of frame allows a later scan; step transition or Reset releases the step guard. Offline preview may remain available, but decoded values cannot submit and no local queue is created.
- **Automated verification:** camera policy tests `5/5` passed, including shared-path eligibility, same-step duplicate suppression, `NOT_FOUND` / `WRONG_LOCATION` failure presentation, manual fallback independence, and offline/quantity blocking. Existing scan execution tests passed `16/16`. The frontend production build passed.
- **Field verification:** this execution environment has no real PDA camera/permission surface, so rear-camera acquisition and live decoding remain pending for field-device acceptance.

**Conclusion:** `PDA_CAMERA_SCAN = PARTIAL`. Implementation and automated gates are complete; promote to `PASS` only after a real PDA/browser verifies permission, rear-camera preview, live location decode, live lot decode, and manual fallback.

## Delivery sequence

1. Camera scanning on real PDA/browser hardware, replacing manual input without changing the session protocol.
2. Offline queue for scanned-but-unconfirmed events only; replay in order and surface conflicts as visible failures without silent overwrite.
3. STAGE and LOAD_VERIFY only after PICK is stable on real hardware.
4. Device enrollment, permissions, diagnostics, and lost-device reset.

Do not combine camera validation and offline replay in one field rollout: operators must be able to distinguish capture failures from synchronization failures.

## Boundary spot-check (2026-09-02)

1. **Authentication:** `/pda` is behind the same application-level login gate as desktop routes and uses the same Zustand JWT store, Bearer interceptor, refresh endpoint, and logout behavior.
2. **Unknown location/lot:** a valid session returns HTTP `200` with a domain event result such as `NOT_FOUND`, `WRONG_LOCATION`, or `PICK_SOURCE_MISMATCH`; the PDA renders the failure and the server keeps the current step unchanged. Missing session/picking resources still use HTTP `404`.
3. **Duplicate protection:** an extra scan during quantity confirmation returns `INVALID_STATE`. Confirmation retries reuse `client_operation_id`; the server returns the original event and does not increment picked quantity twice.
4. **Reset semantics:** reset clears only `current_location_id` and `current_picking_item_id`. It does not roll back confirmed picked quantity and never posts or clears inventory. Ending a partial session likewise preserves the confirmed picking progress without completing the outbound order.
5. **Offline semantics:** visual offline state plus submission gating only; no local queue exists yet.

## Acceptance gate for the first slice

- Production frontend build passes.
- An authorized operator can create and restore a PDA PICK session.
- Scanner Enter input advances location and lot steps without touch interaction.
- Quantity confirmation uses a retry-stable client operation ID.
- Duplicate, mismatch, invalid-state, permission, and connectivity failures are visible and do not advance local state optimistically.
- Completing or partially ending the session uses the existing backend transition.
- Existing desktop workflows and backend contracts remain unchanged.
