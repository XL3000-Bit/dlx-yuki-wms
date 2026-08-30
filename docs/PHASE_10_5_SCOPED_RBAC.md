# PHASE 10.5 Scoped RBAC & Data Visibility Foundation

Branch: `phase-10.3-work-order-audit`.
Inspection first: `docs/CURRENT_AUTH_RBAC_ASSESSMENT.md`.
This phase does not start PHASE 10.6.

## Current auth assessment

See the assessment file. Summary: JWT + single `User.role` enum. Write deps are role-only. No warehouse or customer row scope existed. Global Search ignored the caller. VIEWER could read every operational record.

## Scope model

- `users.warehouse_scope_mode` / `users.customer_scope_mode`: `ALL` | `SELECTED`
- `user_warehouse_scopes` (`user_id`, `warehouse_id`) UNIQUE
- `user_customer_scopes` (`user_id`, `customer_id`) UNIQUE
- ADMIN is always treated as ALL in `get_access_scope`
- Policy helpers live in `app/services/access.py`

## Roles

Existing enum reused. No new inheritance tree.

| Role | Read in scope | Warehouse write | Outbound/Load write | Manage users |
| --- | --- | --- | --- | --- |
| ADMIN | ALL | yes | yes | yes |
| MANAGER | scoped | yes | yes | no |
| INBOUND | scoped | yes | no | no |
| OUTBOUND | scoped | no | yes | no |
| WAREHOUSE | scoped | yes | yes | no |
| VIEWER | scoped | no | no | no |

## Permissions

No new permission catalog. Existing deps reused:

- `require_admin`
- `require_warehouse_write`
- `require_outbound_write`

Frontend maps those to `usePermissions()` flags. Backend remains enforcement.

## Warehouse scope

SELECTED users only see assigned warehouses. Empty assignment sees nothing. Out-of-scope detail returns **404**.

Enforced on Load, Work Order, Exception list/detail/write, Global Search, warehouse master dropdowns, and parent-scoped History endpoints.

## Customer scope

Enforceable where `customer_id` FK exists: Inbound, Inventory, FBA, Outbound (search applies it on those types).

NOT ENFORCEABLE YET: Load, Work Order, Exception, Container Tracking (`customer_reference` string only).

## Read / write enforcement

Read and write use the same warehouse id set. Role still decides whether a write dep passes. Frontend selected warehouse is not authorization.

## Global Search

`search(db, q, limit, user)` filters every type by warehouse visibility. Ranking and grouped response unchanged. EXCEPTION type included. Leak tests cover exact / prefix / contains / mixed.

## Related-object lookup

Warehouse master list is scoped. Load create still validates outbound warehouse match. Work Order / Exception keep existing warehouse mismatch 409. Out-of-scope parents 404 through scoped get helpers.

## Trouble Shoot / Load / Work Order / History

Exception list, counts, detail, events, create, assign, resolve use one scope. Events inherit the parent. Actor payload stays display fields only.

## Frontend permission UX

`frontend/src/hooks/usePermissions.ts` reads `/users/me`. Pages should use this hook instead of hard-coded role strings. UX only; backend re-checks.

## Migration

`backend/alembic/versions/20260830_0018_scoped_rbac.py` revises `20260830_0017`.

## Backward compatibility

Existing users default to ALL / ALL so current operators do not lose data after migrate. Tighten non-admins to SELECTED via `PATCH /users/{id}/scope`.

## Security tests

`backend/tests/test_scoped_rbac.py`: admin vs warehouse A user, list/detail/search/counts/events/write/master lookup.

## Known limitations

- Inbound / Inventory / FBA / Outbound list endpoints are not fully converted in this pass; Search and the 10.x operations stack are. Remaining modules should call the same helpers next.
- Container rows with null warehouse_id are hidden from SELECTED users.
- No SSO, field-level ACL, notifications, SLA, or portals.
- Remote branch was missing some local-only 10.3 event contract details; History visibility is enforced on the events routes present in this tree.
