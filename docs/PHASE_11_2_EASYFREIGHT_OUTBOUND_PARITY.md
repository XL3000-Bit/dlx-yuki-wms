# PHASE 11.2 — EasyFreight Outbound Parity Matrix

> **Reference structure captured; functional parity not yet established.**

**Implementation gate:** NOT READY FOR PARITY IMPLEMENTATION

Controlled behavior-capture evidence:

- [Action matrix](parity/easyfreight-outbound/EASYFREIGHT_OUTBOUND_ACTION_MATRIX.md)
- [Status matrix](parity/easyfreight-outbound/EASYFREIGHT_OUTBOUND_STATUS_MATRIX.md)
- [Sanitized API observations](parity/easyfreight-outbound/EASYFREIGHT_OUTBOUND_API_OBSERVATIONS.md)
- [Visual measurements](parity/easyfreight-outbound/EASYFREIGHT_OUTBOUND_VISUAL_MEASUREMENTS.md)
- [Gap analysis](parity/easyfreight-outbound/EASYFREIGHT_OUTBOUND_GAP_ANALYSIS.md)

## Status and evidence boundary

**Capture date:** 2026-08-30

**Source:** authenticated EasyFreight Outbound page at `/admin/v2/outbounds`

**Mode:** read-only browser inspection of rendered controls and DOM metadata.

No authentication material was read or recorded. No create, confirm, exception,
dispatch, cancel, delete, export, or other business mutation was submitted. The
Create Outbound form was opened without entering data and closed with its Cancel
button.

Evidence vocabulary in this baseline records source observations. Parity state in
the controlled-capture documents is limited to MATCHED, PARTIAL, MISSING,
BLOCKED, UNKNOWN, INTENTIONAL_DIFFERENCE, and NOT_APPLICABLE.

**Operator-video addendum (2026-09-03):** a supplied 67-second recording directly
shows multi-row OB selection followed by the Delete action and a confirmation
dialog. The recording stops before the confirmation result, so it establishes the
selection/confirmation interaction but not EasyFreight's deletion rules, side
effects, or post-confirm response.

Source-evidence vocabulary:

- **CONFIRMED** — directly visible in the rendered page or control metadata.
- **PARTIAL** — a comparable DLX capability exists, but fields or behavior differ.
- **UNKNOWN** — the behavior would require a business mutation, network capture,
  or another page that was not exercised in this read-only pass.

## EasyFreight workbench composition

The page is a three-zone outbound operations workbench rather than one flat list:

1. the primary Outbound/OB list;
2. the selected OB's `OB BOL List`;
3. a `Remaining BOL List` used as the unassigned candidate pool.

During capture, the primary list count moved between 12,418 and 12,423 and the
OB BOL count moved between 8,191 and 8,192; the Remaining BOL list showed 340.
These are volatile source-system snapshots, not parity constants. They are
recorded only as evidence that all three areas paginate independently.

## Primary OB list

### Actions

| Action | Observed state | Result evidence |
| --- | --- | --- |
| Delete | Visible; multi-row confirmation invoked in the 2026-09-03 operator video | Confirmation interaction CONFIRMED; post-confirm result UNKNOWN. |
| Cancel | Visible | UNKNOWN; not invoked. |
| Confirm OB | Visible | UNKNOWN; not invoked. |
| Exception | Visible | UNKNOWN; not invoked. |
| Create OB | Visible; form inspected | Form fields CONFIRMED; submission not invoked. |
| Refresh | Visible; invoked after a safe filter change | Retained the applied filtered result. |
| Reset Window | Visible; invoked | Confirmed as a layout command rather than a filter reset; persistence remains UNKNOWN. |
| Hide OB BOL List | Visible; hide/show invoked and restored | Confirms the right-side list visibility control. |

### Filters

| Label | Rendered field name or options |
| --- | --- |
| ID | `ids` |
| Status | New, Confirmed, Cargo Loaded, Partially Shipout, Fully Shipout, Exception, Canceled |
| Type | TBD, Direct, Consol, Redirect |
| Delivery Type | TBD, FBA, FBM, UPS, FedEx, Order Fulfillment, Self Pickup, USPS, MIX, DHL, Walmart |
| Pickup Location | `pickup_locations` |
| Delivery Location | `delivery_locations` |
| Carrier | `carriers` |
| BOL# | `bol_ids` |
| CNTR#/IB# | `ib_numbers` |
| SKD PU Date | `scheduled_pickup_times` |
| Redirect Location | `redirect_locations` |
| ISA/FBA/MARKING/REF# | `searches` |
| DEL REF# | `delivery_references` |
| Agent Code | `agent_codes` |

### Columns

`OB#`, Status, Carrier Code, Loading Team, Truck Type, Notify Carrier,
Delivery Type, Pickup Location, Schedule PU, DEL APT TIME, OB Type, DEL,
Redirect, Booked Qty, ISA/DEL APT#, DEL REF#, WHS Remark, and OB BOL.

Each row also exposes a selection checkbox and a `Show` control for related BOL
content. The primary list supports 10, 20, 50, 100, 200, 500, and 1,000 rows per
page in the observed UI.

## OB BOL List

### Actions and filters

The toolbar contains `Mange Properties`, Views, Show/Hide Filters, Awaiting
Dispatch, Refresh, Export, an unlabeled icon action, disabled Batch Update
Transfer Code, and Active Filters. `Mange Properties` is retained here exactly
as displayed; it should not be copied as a DLX label.

| Filter | Options or field evidence |
| --- | --- |
| BOL# / OB# | `id` / `ob_number` |
| Status | Pre, Confirmed, In Transit, Delivered, Exception, Canceled |
| Pickup / Delivery / Redirect Location | Named location controls |
| Customer | Named customer control |
| Transfer Code | Named transfer-code control |
| Reference ID | `receiver_reference_id` |
| Receiver Shipment ID | `receiver_shipment_id` |
| Group Status | Pre-Alert, Arrived at Port, At WHS Yard, WHS Received |
| CNTR | `container_number` |
| Type | FBM, FBA, UPS, FedEx, Work Order, Other, Order Fulfillment, Temporary Storage, Self Pickup, USPS, DHL, Walmart |
| Ready To Ship | Ready To Ship, Hold |
| Urgent | Yes, No |
| Date Type | APT, Out Gate, ETA, Unloading Date, LFD |
| Date range | Two date controls; APT was the initial date type |
| ISA/FBA/MARKING/REF# | `dispatchSearches` |
| Agent Code | `dispatchAgentCodes` |

### Columns and totals

`BOL#`, Type, Group Status, Pickup Location, Del Code, Redirect Code,
Transfer Code, Weight LB, CBM, Est. OB PLT, WHS PLT, DW, ETA, APT,
Unloading Date, LFD, Custom Status, Out Gate, Remark, Dispatch, Ready,
CNTR#, Agent Code, Customer, Receiver Shipment ID, Reference ID, Status, and
Urgent.

The grid displays Selected and Total summaries for weight, CBM, estimated
pallets, and warehouse pallets. It has its own row selection and pagination.

## Remaining BOL List

The toolbar contains Active Filters, Show/Hide Filters, Refresh, and Export.

### Filters

`BOL#`, `OB#`, Status, Pickup Location, Delivery Location, Redirect Location,
Customer, Group Status, CNTR, Ready To Ship, Type, Urgent, Act IB Date range,
and Est. IB Date range. Status, Group Status, readiness, type, and urgency use
the same option families documented for the OB BOL list where applicable.

### Columns and totals

`OB BOL#`, Type, Status, Pickup Location, Del Code, Redirect Code, Act. IB
Date, Est. IB Date, Remaining PLT, and CNTR#. The list displays a Remaining PLT
total and has independent pagination.

## Create Outbound form

Opening `Create OB` replaces the primary work area with a `Create Outbound`
form. The following fields are CONFIRMED:

| Field | Observed behavior/options |
| --- | --- |
| OB# | Disabled; generated automatically. |
| OB Type | TBD, Direct, Consol, Redirect. |
| Delivery Type | Default label displayed as `TDB`; FBA, FBM, UPS, FedEx, Order Fulfillment, Self Pickup, USPS, MIX, DHL, Walmart. |
| Truck Type | TBD, 53' FTL, LTL, 26' FTL, Floor loaded, 30' FTL. |
| Carrier | Searchable selection; default TBD. |
| Schedule Pickup Time | Date/time field. |
| Pickup Location | Searchable selection; default TBD. |
| Delivery Apt Time | Date/time field. |
| Booked PLT | Quantity field. |
| ISA/DEL APT# | Reference field. |
| DEL REF# | Reference field. |
| Related OB BOL List | Required drag-and-drop target for one or more OB BOL records. |

The related-BOL table contains OB BOL#, Type, Status, Pickup Location,
Delivery Apt Time, Del Code, Redirect Code, Act. IB Date, ETA, Est. OB PLT,
Remaining PLT, Weight, and Action. Cancel and Create buttons are present. The
observed source label `TDB` appears to be a typo and should not become a DLX
contract.

## Initial parity matrix

| Capability | EasyFreight evidence | Current DLX baseline | PHASE 11.2 disposition |
| --- | --- | --- | --- |
| Three-zone workbench | CONFIRMED | PARTIAL: primary Outbound list plus selected OB allocated/BOL and remaining inventory panels. | Preserve the DLX page-scroll layout; make the three data roles explicit. |
| Master OB search/filter | Dense reference, location, date, carrier, type, and status filters. | PARTIAL: unified reference search plus status, OB type, warehouse, and carrier. | Add only filters backed by stable DLX fields and server queries. Do not create display-only filters. |
| OB lifecycle vocabulary | New through partial/full shipout plus exception/cancel. | PARTIAL: New, On Hold, In Progress, Confirmed, Dispatched, Completed, Canceled, Exception. | Create an explicit semantic mapping before changing labels or transitions. |
| OB columns | 19 operational columns plus selection/expansion. | PARTIAL: broad dispatch columns exist, but EasyFreight-specific team, notify, DEL, and redirect semantics are not all equivalent. | Map field-by-field; mark unsupported source concepts instead of inventing data. |
| Create OB | Rich scheduling fields and required related-BOL drag/drop. | PARTIAL: DLX Create OB captures warehouse, customer, carrier, type, and reference. | Separate OB header creation from shipment allocation unless the existing transaction boundary safely supports both. |
| Create Load | Action requested and PostgreSQL-smoke-verified in the DLX baseline. | CONFIRMED in DLX for selected OBs from one resolved warehouse. | Retain DLX warehouse-resolution validation. EasyFreight result remains UNKNOWN in this pass. |
| Delete | Multi-row selection and confirmation CONFIRMED; post-confirm result UNKNOWN. | CONFIRMED in DLX for pristine NEW drafts only; linked or execution-started records are rejected per row and successful deletion is audited. | Intentional safety boundary until source deletion semantics are established. |
| Confirm / Dispatch / Complete / Cancel | Entry points visible; mutation results UNKNOWN. | CONFIRMED in the validated DLX lifecycle baseline. | Keep backend `allowed_actions` authoritative; avoid inferring state from labels. |
| Exception / Resolve Exception | Exception entry point visible; resolve behavior not exercised. | CONFIRMED in the validated DLX lifecycle baseline, including reason/remark capture. | Preserve DLX exception history and transaction behavior. |
| OB BOL candidate management | Dedicated list with selection, readiness, dispatch, transfer, references, dates, and summaries. | PARTIAL: allocated shipment/BOL panel exists; DLX now supports checked multi-row drag from Remaining Source to Allocation and back, with per-row partial-failure feedback. | Identify which remaining concepts map to loads, documents, or container tracking before UI expansion. |
| Remaining candidate pool | Dedicated filterable/paginated BOL list with remaining-pallet total. | PARTIAL: Remaining Shipment / Inventory List exists. | Confirm quantity and identity mapping; keep remaining quantities server-derived. |
| Saved views/property management | Visible `Views` and property-management controls. | Not established by this capture. | Out of parity scope unless an existing DLX preference contract is found. |
| Export | Visible in both subordinate lists. | PARTIAL: filtered/selected outbound exports exist. | Verify export dataset semantics separately; do not expose a permanently disabled action. |
| Filter request contract | Client-bound named controls; no native form action or method. | Existing DLX queries are URL/server parameter based. | UNKNOWN for EasyFreight endpoint, HTTP method, payload, debounce, and response schema until a safe request trace is authorized. |

## Operation-result evidence still required

The following source-system results remain deliberately unverified because a
read-only production inspection cannot safely establish them:

- validation and persistence rules for Create OB;
- exact state transitions and side effects for Confirm OB, Exception, Cancel,
  Delete after confirmation, and Awaiting Dispatch;
- partial-versus-full dispatch calculation;
- concurrency, idempotency, and duplicate-submit behavior;
- which operation refreshes each of the three lists;
- API endpoints, request payloads, error contracts, and response schemas;
- permission differences for Viewer, warehouse-scoped, and cross-warehouse users.

These items require a non-production test account/fixture, approved safe records,
or source/API documentation. They must not be guessed from button labels.

## Implementation gates

No DLX business page or API is changed by this baseline. Before implementation:

1. define the EasyFreight-to-DLX status and identity mappings;
2. map every proposed filter and column to an existing server-owned field;
3. preserve DLX inventory, allocation, load, exception, and lifecycle transaction
   boundaries already verified against PostgreSQL;
4. separate confirmed parity requirements from source-specific labels and typos;
5. validate any mutating parity workflow in an isolated PostgreSQL fixture before
   browser smoke.
