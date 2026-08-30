# PHASE 10.1 — Load Management Foundation

## Domain model

`Load` is an outbound-level transportation aggregate. It owns operational transport facts that should not be copied to every outbound: carrier, appointment, destination, driver/tractor/trailer and seal. An `OutboundOrder.load_id` nullable foreign key provides the one-load-at-a-time relationship while allowing unassigned orders.

## Database

Migration `20260829_0013_load_management` creates `loads`, indexes `load_no` (unique), status, warehouse, carrier, appointment and creator, and adds the indexed `outbound_orders.load_id` FK. No JSON IDs or old migration edits are used.

## Relationships and totals

Loads reference Warehouse, optional Carrier and creator. Outbound allocations remain the source of pallet/carton/weight/CBM totals through the existing `outbound.services.totals` helper; Load does not duplicate calculation rules. Detail returns per-OB summary rows and aggregate totals.

## Status

`PLANNED → READY → DISPATCHED → COMPLETED`; planned/ready may transition to `CANCELED`. Terminal completed/canceled loads are immutable. Assignment is rejected for completed/canceled outbound orders and for loads after dispatch.

## API

- `GET /api/v1/loads` — bounded list filters for query, status, warehouse and appointment date.
- `GET /api/v1/loads/{id}` — detail and outbound summaries.
- `POST /api/v1/loads` — create empty or with outbound IDs.
- `PATCH /api/v1/loads/{id}` — update transport fields before terminal status.
- `POST /api/v1/loads/{id}/outbounds` and `DELETE /api/v1/loads/{id}/outbounds/{outbound_id}` — membership management.
- `POST /api/v1/loads/{id}/status` — validated transition.

Writes use existing outbound-write permission; reads use the existing authenticated read dependency.

## UI and outbound integration

Operations → Loads is a compact Ant Design list with search/status/warehouse filters, create modal and drawer detail. Detail contains Overview, Outbound Orders, Dispatch Information and honest Documents/History placeholders. Outbound Dispatch adds Create Load beside Selected Export; it requires selected OBs, rejects mixed warehouses, does not alter OB lifecycle state, and offers an Open Load action after success.

## Global Search integration

The existing Phase 10.0 grouped search now includes `LOAD`/`load_no` as an additional model. Existing ranking, limits and groups are unchanged. A result navigates to `/loads?selected=<id>` and opens the existing Load drawer.

## Validation

The service validates warehouse/carrier existence, duplicate outbound IDs, cross-warehouse membership, duplicate active assignment, terminal membership rules and status transitions. Unique load numbers use `LD-YYYYMMDD-XXXX` with a database unique index.

## Tests

Added Load tests cover creation, uniqueness format, one/multiple assignment, duplicate assignment, cross-warehouse rejection, removal, list/detail totals, transitions, terminal behavior, authentication and global search. Existing 82 Phase 10.0 tests remain green.

## Known limitations

This is not a TMS: no route optimization, GPS, EDI, carrier portal, POD workflow, accounting, work orders or automatic load optimization. Documents/history are placeholders until a durable history/document foundation exists. Concurrent number generation is serialized by the database uniqueness guarantee; PostgreSQL advisory locking can be added if high-concurrency numbering becomes necessary.
