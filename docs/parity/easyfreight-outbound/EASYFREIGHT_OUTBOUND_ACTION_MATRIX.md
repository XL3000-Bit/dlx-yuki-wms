# EasyFreight Outbound Action Matrix

## Capture boundary

**Date:** 2026-08-30

**State:** Reference structure captured; functional parity not yet established.

The authenticated production page was inspected non-destructively. No record was
created, selected for mutation, assigned, released, confirmed, dispatched,
canceled, deleted, exported, or otherwise changed. No safe test record or
synthetic-record authorization was provided, so write-path results remain
BLOCKED rather than inferred from labels.

## Primary Outbound list

| Action | Source evidence | Parity state | Safe result evidence |
| --- | --- | --- | --- |
| Create OB | Button and form structure visible. Generated OB number, header fields, and required related-BOL target were observed. | PARTIAL | Form structure is known; validation, persistence, permissions, idempotency, and resulting status are BLOCKED. |
| Delete | Visible and enabled without a selected record in the captured state. | UNKNOWN | Selection requirements, confirmation dialog, hard/soft-delete semantics, and permissions are BLOCKED. |
| Cancel | Visible and enabled without a selected record in the captured state. | PARTIAL | DLX has a validated cancel action, but EasyFreight transition rules and side effects are BLOCKED. |
| Confirm OB | Visible and enabled without a selected record in the captured state. | PARTIAL | DLX has a validated confirm action; EasyFreight prerequisites, resulting state, and list refresh behavior are BLOCKED. |
| Exception | Visible and enabled without a selected record in the captured state. | PARTIAL | DLX has exception and resolution behavior; EasyFreight reason fields, resolution path, and history effects are BLOCKED. |
| Refresh | Invoked after a safe filter change. | MATCHED | Refresh retained the server-side filtered result and did not clear it. |
| Reset Window | Invoked without mutating business data. | PARTIAL | It is a layout action, not a filter reset. It did not visibly reset the tested right-pane scroll position. Persistence semantics are UNKNOWN. |
| Hide / Show OB BOL List | Both states were invoked. | MATCHED | Hiding removed the right pane; showing restored it. No business data changed. |

## OB BOL List

| Action | Source evidence | Parity state | Safe result evidence |
| --- | --- | --- | --- |
| Mange Properties | Opens a property panel with 29 additional visible property checkboxes. | PARTIAL | Opening/closing is confirmed. Saving, scope, defaults, and shared-view effects are UNKNOWN; no property was changed. The source label contains a typo. |
| Views | Opens an additional input/control surface. | UNKNOWN | View identity, persistence, ownership, sharing, and reset behavior were not safely established. No view was saved or modified. |
| Show / Hide Filters | Invoked and restored. | MATCHED | The top list added its filter controls independently of the lower list. |
| Awaiting Dispatch | Visible. | UNKNOWN | Query semantics and whether it mutates or merely filters are BLOCKED. |
| Refresh | Visible. | PARTIAL | The primary refresh was verified; subordinate refresh result semantics remain UNKNOWN. |
| Export | Visible. | PARTIAL | Dataset scope, selected-versus-filtered behavior, format, permissions, and redaction are BLOCKED because export was not invoked. |
| Unlabeled icon action | Visible 35-pixel icon-only control. | UNKNOWN | Accessible name and behavior were not established without invoking it. |
| Batch Update Transfer Code | Disabled with no selection. | PARTIAL | Selection gating is visible. Mutation fields, validation, atomicity, and permissions are BLOCKED. |
| Row selection | Checkboxes and Selected totals are visible. | PARTIAL | Aggregate selection affordance exists; cross-page selection and action scope are UNKNOWN. |
| Assignment / release | Two candidate lists and selection affordances are visible. | UNKNOWN | Exact direction, quantity rules, partial assignment, release behavior, and transaction boundaries are BLOCKED. |

## Remaining BOL List

| Action | Source evidence | Parity state | Safe result evidence |
| --- | --- | --- | --- |
| Show / Hide Filters | Invoked and restored independently. | MATCHED | The lower list added its own filter controls without opening the upper filters. |
| Refresh | Visible. | UNKNOWN | Result retention and refresh relationships with the other two lists were not invoked. |
| Export | Visible. | PARTIAL | Scope, format, permissions, and data redaction are BLOCKED. |
| Candidate selection | Row-selection structure and Remaining PLT summary are visible. | PARTIAL | Selection-to-assignment behavior and quantity semantics are BLOCKED. |

## Read-only control behavior

| Behavior | Evidence | Parity state |
| --- | --- | --- |
| Status filter | Selecting New refreshed immediately and returned 20 visible New rows; the select then rendered blank. | PARTIAL |
| Combined filters | Status New plus Type Consol produced visible rows satisfying both observed categories, consistent with AND semantics. | PARTIAL |
| Delivery Type filter | Selecting FBA did not produce the expected visible category values in the mapped Delivery Type column. | UNKNOWN |
| Filter state display | Applied selects rendered blank after their automatic refresh. | MISSING |
| Primary pagination | Page 1 to page 2 changed only the primary pager; subordinate pagers stayed on page 1. | MATCHED |
| Page-size options | Primary supports 10, 20, 50, 100, 200, 500, and 1,000. Right-top displayed 10 by default. | PARTIAL |
| Text search | No production identifier was entered. | BLOCKED |
| Sorting | No sort was changed because safe reset and server-side scope were not established. | BLOCKED |
| Filter reset | No dedicated reset-filters control was confirmed; Reset Window is a layout command. | MISSING |

## Mutation gate

The following must be captured with an approved non-production fixture, source
documentation, or an explicitly designated safe record before implementation:

- Create OB validation, duplicate submission, result record, and transaction;
- Confirm OB, Exception, Resolve Exception, Cancel, and Delete transition rules;
- assignment and release direction, quantities, partial completion, and refresh;
- permission differences by role and warehouse scope;
- success, validation, conflict, authorization, and server-error outcomes.

**Recommendation:** NOT READY FOR PARITY IMPLEMENTATION
