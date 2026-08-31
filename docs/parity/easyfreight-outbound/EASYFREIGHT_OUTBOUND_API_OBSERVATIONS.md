# EasyFreight Outbound Sanitized API Observations

## Safety statement

No authentication headers, cookies, session identifiers, CSRF values, local
storage, storage state, passwords, tokens, credential material, raw request
bodies, raw response bodies, or HAR files were read or recorded. Only rendered
page behavior and non-sensitive URL metadata were observed.

## Page and request boundary

| Observation | Sanitized evidence | Parity state |
| --- | --- | --- |
| Entry page | HTTPS host admin.unicanginc.com, path /admin/v2/outbounds | MATCHED |
| Initial URL state | No query keys were present. | PARTIAL |
| Filter transport | URL remained without query keys after observed auto-refreshes. | UNKNOWN |
| API endpoint | Not captured. | BLOCKED |
| HTTP method | Not captured. | BLOCKED |
| Request payload schema | Not captured. | BLOCKED |
| Response schema | Not captured. | BLOCKED |
| Authentication mechanism | Deliberately not inspected. | BLOCKED |
| Error contract | No safe validation, conflict, permission, or server-error request was generated. | BLOCKED |

## Rendered control names

The DOM exposed non-sensitive control names that may help later map an approved
request trace. These are UI observations, not a confirmed backend contract:

| Area | Observed names |
| --- | --- |
| Primary list | ids, pickup_locations, delivery_locations, carriers, bol_ids, ib_numbers, scheduled_pickup_times, redirect_locations, searches, delivery_references, agent_codes |
| OB BOL list | id, ob_number, receiver_reference_id, receiver_shipment_id, container_number, dispatchSearches, dispatchAgentCodes |

## Read-only interaction observations

| Interaction | Sanitized outcome | Parity state |
| --- | --- | --- |
| Select Status New | Automatic refresh occurred; 20 visible rows shared the selected status category. The control display then became blank. | PARTIAL |
| Add Type Consol | Visible rows satisfied both observed categories, consistent with AND composition. | PARTIAL |
| Add Delivery Type FBA | Visible Delivery Type values did not match the selected category in the mapped column. | UNKNOWN |
| Refresh | Retained the already applied source-side result. | PARTIAL |
| Primary Next page | Primary pager moved to page 2 while both subordinate pagers stayed on page 1. | MATCHED |
| Full page reload | Restored the default visible filter state and page 1. | PARTIAL |

## Volatile quantity snapshot

At one read-only snapshot, the three independent pagers showed:

| List | Page size | Page range | Total |
| --- | ---: | ---: | ---: |
| Primary Outbound | 20 | 1 of 622 | 12,423 |
| OB BOL List | 10 | 1 of 820 | 8,191 |
| Remaining BOL List | 10 | 1 of 34 | 340 |

The source changed during the capture window, so these values are evidence of
independent server-backed collections only. They must not become tests or
product constants.

The OB BOL grid exposed Selected and Total summaries for Weight LB, CBM,
estimated outbound pallets, and warehouse pallets. The Remaining grid exposed a
Remaining PLT total. Exact snapshot amounts are intentionally omitted because
they are live operational values and do not establish calculation formulas.

## Required approved trace

An approved non-production trace must establish endpoint, method, parameter
encoding, pagination/sort contract, error schema, concurrency behavior, and
refresh dependencies for all three lists and every mutation. The resulting notes
must remain sanitized and must not contain raw HAR or authorization material.

**Recommendation:** NOT READY FOR PARITY IMPLEMENTATION
