# PHASE 10.5 — Scoped RBAC & Data Visibility Foundation

## Policy model

Authorization has two independent layers:

1. A role-derived permission decides whether the user may read or mutate a class of operation.
2. Warehouse and customer scopes decide which business records that permission can reach.

The existing roles remain the compatibility contract: `ADMIN`, `MANAGER`, `INBOUND`, `OUTBOUND`, `WAREHOUSE`, and `VIEWER`. They map to the small permission set `read`, `manage_inbound`, `manage_outbound`, `manage_warehouse`, and `manage_users`. `ADMIN` has every permission and always has effective `ALL` data scope; `VIEWER` has `read` only. The operationally specialized roles are retained instead of introducing a second, overlapping `OPERATOR` role.

## Scope storage and administration

Each user has independent `warehouse_scope_mode` and `customer_scope_mode` values of `ALL` or `SELECTED`. Selected IDs are stored in `user_warehouse_scopes` and `user_customer_scopes`. Administrators update a user's complete scope through `PATCH /api/v1/users/{user_id}/scope`; unknown IDs are rejected.

`GET /api/v1/users/me` returns the role-derived permissions, both effective scope modes, and the allowed warehouse/customer IDs. Frontend controls use this response for action visibility, while the backend remains authoritative.

## Enforcement rules

- Mandatory predicates are applied before pagination, totals, aggregation, export, workbench calculation, or search ranking.
- A record must satisfy every real scope relationship it owns: warehouse and customer where both foreign keys exist.
- Scoped-out detail resources return `404`, preventing existence disclosure.
- Create and update paths validate submitted warehouse/customer IDs. Parent attachments (for example outbound orders on a load) are independently checked and must remain warehouse-compatible.
- Work-order events inherit the work order's warehouse visibility. Exception events inherit their exception's visibility. Picking lists and BOLs inherit their outbound order's visibility.
- Global search applies the same predicates to each entity query, covering exact, prefix, contains, and mixed-result searches.
- Warehouse, customer, area, and location selectors return only allowed records.
- Container dispatch aggregates are scoped before grouping so shared container numbers cannot reveal another warehouse's schedule or counts.

## Module coverage

Scope enforcement covers inbound, inventory, FBA, outbound, outbound/FBA workbenches, container tracking, loads, work orders and event history, operational exceptions and event history, picking/BOL, master-data selectors, exports, and global search. Trouble Shoot list totals, counts, detail, create, assign, and resolve all share the same policy.

## Customer-scope boundary

Customer scope is enforced only through real foreign keys. Container tracking has an optional warehouse relationship and no customer foreign key, so customer scope cannot safely be inferred from customer-reference text. Rows without a warehouse relationship are visible only to effective `ALL` warehouse users; selected-scope users cannot access or import them. Carrier and Amazon FC reference data are global because they have no customer ownership relationship.

## Backward compatibility and rollout

Migration `20260830_0018` creates the scope enum, two user scope columns, and both mapping tables. Existing and newly created users default to `ALL` so deployment does not silently remove current access. Administrators retain unconditional `ALL`. Narrow non-admin accounts to `SELECTED` after assigning their allowed IDs.

Recommended rollout order:

1. Apply the Alembic migration.
2. Verify administrator access and `/users/me` responses.
3. Assign warehouse/customer IDs to selected non-admin users.
4. Change those users' modes to `SELECTED` in the same scope update.
5. Run the cross-warehouse security matrix and module regression suite.

## Explicit non-goals

This foundation does not add SSO, external identity providers, per-field ACLs, arbitrary custom-role builders, inferred customer ownership, or a policy-expression language.
