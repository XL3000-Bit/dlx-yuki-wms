# EasyFreight Outbound Gap Analysis

## Current state

**Reference structure captured; functional parity not yet established.**

The structure, visible vocabulary, filter controls, independent pagination,
three-grid geometry, splitter behavior, and non-mutating filter composition have
been captured. Functional parity cannot be claimed until source mutation,
quantity, permission, and error contracts are established safely.

## Critical unknowns

| Gap | Why it blocks implementation | Parity state | Safe evidence required |
| --- | --- | --- | --- |
| Create OB contract | Required-field, related-BOL, duplicate-submit, transaction, and result-state rules are unverified. | BLOCKED | Non-production fixture or approved synthetic record plus sanitized request/result evidence. |
| Lifecycle transitions | Confirm, Exception, Resolve, Cancel, Delete, and Awaiting Dispatch state guards and side effects are unverified. | BLOCKED | State-by-action matrix with valid and invalid outcomes. |
| Assignment / release | The role of the OB BOL and Remaining BOL lists is visible, but movement direction, partial quantity, identity, and atomicity are unverified. | BLOCKED | Approved selection, assignment, release, and repeated-submit cases. |
| Quantity denominators | Selected/Total and Remaining PLT displays exist, but formulas and update timing are unverified. | BLOCKED | Before/after snapshots from isolated records with known quantities. |
| Delivery Type filter | Selecting FBA did not match visible values in the mapped Delivery Type column. | UNKNOWN | Sanitized server request plus field-mapping confirmation. |
| API/error contract | Endpoints, methods, payloads, response schemas, conflicts, validation, and retry behavior are unknown. | BLOCKED | Approved sanitized trace without credentials or raw HAR. |
| Permission matrix | Viewer, operator, warehouse-scoped, and cross-warehouse outcomes were not tested. | BLOCKED | Approved accounts or source authorization documentation. |

## High-priority gaps

| Gap | Current evidence | Parity state |
| --- | --- | --- |
| Text search | Controls are visible; no live production identifier was submitted. | BLOCKED |
| Sort semantics | Column labels are captured; server/client ordering and stable tie-breakers are unknown. | BLOCKED |
| Filter reset | No dedicated reset-filters action was identified; applied selects visually clear after refresh. | MISSING |
| Saved views | Control exists; ownership, sharing, save/reset, and permissions are unknown. | UNKNOWN |
| Column preferences | Panel structure exists; persistence and default restoration are unknown. | UNKNOWN |
| Export | Buttons exist; dataset scope, selection rules, format, and authorization are unknown. | UNKNOWN |
| Refresh dependencies | Primary refresh retention is known; cross-refresh of all three lists is unknown. | UNKNOWN |
| Splitter persistence | Responsive geometry is known; saved width and reset behavior are unknown. | UNKNOWN |
| Unlabeled icon | A control is visible without a confirmed accessible name or purpose. | MISSING |

## Confirmed structural reference

| Area | Captured evidence | Parity state |
| --- | --- | --- |
| Primary Outbound grid | Actions, filters, 19 data columns, page-size options, and independent pagination. | PARTIAL |
| OB BOL grid | 28 data columns, filters, selected/total summaries, column controls, and independent pagination. | PARTIAL |
| Remaining BOL grid | 10 data columns, filters, remaining-pallet total, and independent pagination. | PARTIAL |
| Split layout | Resizable primary/right split with hide/show and nested right-side scrolling. | PARTIAL |
| Filter composition | Status plus Type behaved as an apparent AND; automatic refresh was observed. | PARTIAL |

## Intentional DLX boundaries to preserve

| Boundary | Disposition | Parity state |
| --- | --- | --- |
| Server-owned lifecycle actions | Keep DLX allowed-actions and PostgreSQL transaction rules authoritative. | INTENTIONAL_DIFFERENCE |
| Inventory and remaining quantities | Keep quantities server-derived; do not reproduce display math without a proven source formula. | INTENTIONAL_DIFFERENCE |
| Source typos | Do not copy Mange Properties or TDB labels. | INTENTIONAL_DIFFERENCE |
| Page structure | Reference three data roles, not necessarily the same overflow-heavy pixel layout. | INTENTIONAL_DIFFERENCE |
| Unsupported source concepts | Mark unsupported fields explicitly instead of fabricating DLX data. | INTENTIONAL_DIFFERENCE |

## Implementation gate

All Critical unknowns must be resolved before business-code work begins. This
capture does not authorize source mutations and does not change the already
validated DLX lifecycle.

**Recommendation:** NOT READY FOR PARITY IMPLEMENTATION
