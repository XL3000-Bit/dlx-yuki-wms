# EasyFreight Outbound Status Matrix

## Evidence boundary

This matrix separates visible vocabulary from verified lifecycle behavior. No
source record was mutated. A matching label does not establish equivalent
transition guards, inventory effects, audit history, terminal-state behavior, or
permissions.

## Outbound status vocabulary

| EasyFreight status | Closest current DLX concept | Parity state | Unresolved semantics |
| --- | --- | --- | --- |
| New | New | PARTIAL | Creation result, editable fields, and allowed next actions are BLOCKED. |
| Confirmed | Confirmed | PARTIAL | Confirmation prerequisites and inventory/allocation side effects are BLOCKED. |
| Cargo Loaded | In Progress or Dispatched | UNKNOWN | Whether this means physical loading, load closure, or dispatch readiness is not established. |
| Partially Shipout | No proven one-to-one label | MISSING | Quantity denominator, partial completion rules, and subsequent actions are BLOCKED. |
| Fully Shipout | Dispatched or Completed | UNKNOWN | Terminal semantics, completion timing, and inventory effects are BLOCKED. |
| Exception | Exception | PARTIAL | Entry reason, resolution transition, and history behavior are BLOCKED. |
| Canceled | Canceled | PARTIAL | Eligible source states, reversal effects, and immutability are BLOCKED. |
| On Hold | DLX-only lifecycle concept | INTENTIONAL_DIFFERENCE | No primary EasyFreight Outbound status with this label was observed. |
| Completed | DLX lifecycle concept | UNKNOWN | It may correspond to Fully Shipout or a downstream event; equivalence is unproven. |

## OB BOL status vocabulary

| EasyFreight OB BOL status | Parity state | Evidence gap |
| --- | --- | --- |
| Pre | UNKNOWN | Initial state and editability are not verified. |
| Confirmed | PARTIAL | Label overlap exists; transition and OB coupling are not verified. |
| In Transit | PARTIAL | Label is operationally familiar; dispatch trigger and reversibility are not verified. |
| Delivered | PARTIAL | Completion/POD relationship and terminal behavior are not verified. |
| Exception | PARTIAL | Exception reason, resolution, and parent propagation are not verified. |
| Canceled | PARTIAL | Cancellation scope and quantity release behavior are not verified. |

## Inbound/group-stage vocabulary exposed in Outbound filters

| Source stage | Parity state | Note |
| --- | --- | --- |
| Pre-Alert | UNKNOWN | Visible as Group Status / Inbound stage filter only. |
| Arrived at Port | UNKNOWN | Visible as a candidate-filter option; no outbound transition was inferred. |
| At WHS Yard | UNKNOWN | Visible as a candidate-filter option; no outbound transition was inferred. |
| WHS Received | UNKNOWN | Visible as a candidate-filter option; no outbound transition was inferred. |

## Transition matrix requiring safe write evidence

| Operation | From-state set | Success target | Invalid-state response | Inventory / quantity effect | Parity state |
| --- | --- | --- | --- | --- | --- |
| Create OB | NOT_APPLICABLE | UNKNOWN | UNKNOWN | UNKNOWN | BLOCKED |
| Confirm OB | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | BLOCKED |
| Exception | UNKNOWN | Exception is suggested by the label only | UNKNOWN | UNKNOWN | BLOCKED |
| Resolve Exception | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | BLOCKED |
| Assign BOL | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | BLOCKED |
| Release BOL | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | BLOCKED |
| Awaiting Dispatch | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | BLOCKED |
| Cancel | UNKNOWN | Canceled is suggested by the label only | UNKNOWN | UNKNOWN | BLOCKED |
| Delete | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | BLOCKED |

## Gate

The status names are captured, but the lifecycle contract is not. No DLX state
machine should be renamed or widened based on this vocabulary alone.

**Recommendation:** NOT READY FOR PARITY IMPLEMENTATION
