# CURRENT_AUTH_RBAC_ASSESSMENT

Source: `XL8776/dlx-yuki-wms` branch `phase-10.3-work-order-audit` @ `f0a81477`.
Date: 2026-08-30.
This file is inspection only. No application code was changed.

## Existing auth

- JWT access + refresh (`app/core/security.py`). `sub` is user id.
- Login / refresh: `POST /api/v1/auth/login`, `/refresh`. No MFA, SSO, or OAuth.
- `get_current_user` in `app/api/deps.py` decodes access token, loads `User`, rejects missing/inactive.
- `CurrentUser` is the default gate on operational GETs. Unauthenticated requests are 401.
- First admin: unauthenticated `POST /users/bootstrap` while user table is empty; forced `ADMIN`.

## Existing roles

`User.role` is a single Postgres enum (`user_role`). No Role table, no Permission table, no user-role M2M.

| Role | Meaning in code today |
| --- | --- |
| ADMIN | User CRUD; inbound delete; included in both write deps |
| MANAGER | Both warehouse write and outbound write |
| INBOUND | Warehouse write only |
| OUTBOUND | Outbound write only |
| WAREHOUSE | Both write deps |
| VIEWER | Default. Authenticated read of all operational APIs |

There are no named permissions such as `VIEW_OPERATIONS` or `MANAGE_LOAD`.

Write dependencies:

- `require_admin`: ADMIN only
- `require_warehouse_write`: ADMIN, MANAGER, INBOUND, WAREHOUSE
- `require_outbound_write`: ADMIN, MANAGER, OUTBOUND, WAREHOUSE

VIEWER is excluded from writes. There is no OPERATOR role.

## Existing warehouse restrictions

- `warehouses` / areas / locations exist. Users have **no** warehouse FK and **no** `user_warehouse_scope` table.
- List endpoints accept optional `warehouse_id` as a **client filter**, not an access scope.
- Detail GET by id does not check caller warehouse.
- Writes check role, not that the target warehouse is assigned to the user.
- Container tracking `warehouse_id` is nullable. Loads, WOs, exceptions, inbound, inventory, FBA, outbound have warehouse FK (container optional).

Conclusion: warehouse scope is **not enforced**. Any authenticated user can list and open every warehouse's records if they know or enumerate ids.

## Existing customer restrictions

- `customers` master exists.
- Real `customer_id` FK: Inbound, InventoryLot, FBAShipment, OutboundOrder (all nullable).
- No `customer_id` on: Load, WorkOrder, OperationalException, ContainerTracking, Picking/BOL (not inspected as having customer FK).
- ContainerTracking has `customer_reference` **string only**. Must not be used as customer scope.
- No `user_customer_scope` table.
- List `customer_id` query params are filters, not authorization.

Customer scope is **NOT ENFORCEABLE YET** on Load, Work Order, Exception, Container Tracking.

## Existing write checks

Role-only. Examples:

- Inbound create/update/receive: `require_warehouse_write`. Delete: `require_admin`.
- Outbound create/update/allocate/status/exception/batch: `require_outbound_write`.
- Load create/update/attach/status: `require_outbound_write`.
- Work Order create/update/status: `require_warehouse_write`.
- Exception create/update/assign/status/resolve/linked WO: `require_warehouse_write`.
- Users create/list: `require_admin`.

Write does **not** verify warehouse or customer membership.

## Missing read checks

All of the following are authenticated-only (`CurrentUser`), with no row scope:

- GET list / detail / export for Inbound, Inventory, FBA, Outbound, Container Tracking, Load, Work Order, Exception
- Exception counts and events
- Work Order events (inherit parent; parent itself is unscoped)
- Global Search `GET /search` — `search(db, q, limit)` receives no user
- Related-object lookups used when creating Load / WO / Exception
- Masters (warehouses, customers) listing for dropdowns

Detail strategy today: missing rows typically 404 from `get_*` helpers; out-of-scope rows still return 200 because scope does not exist.

Recommended 10.5 policy: out-of-scope detail → **404** (do not advertise existence).

## Potential data leakage paths

1. Global Search exact / prefix / contains across all types.
2. Direct `GET /outbounds/{id}`, `/loads/{id}`, `/work-orders/{id}`, `/operational-exceptions/{id}`.
3. Exception events and work-order events by parent id.
4. Create-Load outbound picker; Create-WO related pickers; Create-Exception related pickers.
5. Excel export endpoints (inbound/outbound) dump filtered-or-all rows for any authenticated user.
6. Exception tab `counts` are global, not scoped (same query family as list).
7. VIEWER can read every warehouse and every customer record.
8. Container rows with null `warehouse_id` cannot be warehouse-scoped without an extra rule (treat as admin-only or unscoped-deny for non-ALL users).
9. `/users/me` returns email + role but no scope payload yet; frontend cannot hide warehouses it should not list because `/users/me` and warehouse list are unscoped.

## Module behavior snapshot

| Module | Auth | Read scope | Write check | Customer FK |
| --- | --- | --- | --- | --- |
| Inbound | CurrentUser / warehouse write | optional filter | role | yes (nullable) |
| Inventory | CurrentUser + warehouse write on mutations | optional filter | role | yes (nullable) |
| FBA | CurrentUser + write on mutations | optional filter | role | yes (nullable) |
| Outbound | CurrentUser + outbound write | optional filter | role | yes (nullable) |
| Container Tracking | CurrentUser + write on mutations | optional filter | role | NOT ENFORCEABLE (`customer_reference` string) |
| Load | CurrentUser + outbound write | optional filter | role | NOT ENFORCEABLE |
| Work Order | CurrentUser + warehouse write | optional filter | role | NOT ENFORCEABLE |
| Trouble Shoot | CurrentUser + warehouse write | optional filter | role | NOT ENFORCEABLE |
| Global Search | CurrentUser only | none | n/a | mixed |
| Users | admin except `/me` and bootstrap | n/a | admin | n/a |

## Frontend auth context

- `frontend/src/stores/auth.ts` stores access/refresh tokens in `localStorage` only.
- No current-user object, no role helper, no permission hook, no warehouse scope in client state.
- UI cannot currently hide Create/Resolve by role without a new `/users/me` payload and a shared hook.
- Warehouse selector (AppLayout) is presumed to list all warehouses from masters API.

## Proposed 10.5 direction (not implemented)

Keep `UserRole` enum. Do not add a full permission catalog unless a later phase needs button-level IAM.

Add:

- `user_warehouse_scopes` (`user_id`, `warehouse_id`) UNIQUE + FKs
- `user_customer_scopes` (`user_id`, `customer_id`) UNIQUE + FKs
- `users.warehouse_scope_mode` / `users.customer_scope_mode`: `ALL` | `SELECTED`

Semantics:

- ADMIN → `ALL` warehouses and `ALL` customers (bypass selected rows).
- Non-admin with `SELECTED` + empty assignment → see nothing (safe default).
- Existing users data migration: ADMIN → ALL/ALL; others → ALL/ALL for this upgrade so current single-tenant operators do not lose data. Document that production hardening should switch non-admins to SELECTED after assigning warehouses.

Reusable policy (names to match code style):

- `get_access_scope(db, user)`
- `apply_warehouse_scope(stmt, model.warehouse_id, scope)`
- `ensure_warehouse_visible` / `ensure_warehouse_writable` → 404 on read miss, 404/403 on write miss
- Customer helpers only applied where `customer_id` FK exists

Read and write use the same warehouse id set. Role still gates write vs view.

Next Alembic: `20260830_0018_scoped_rbac.py`, down-revision `20260830_0017_operational_exceptions`.
