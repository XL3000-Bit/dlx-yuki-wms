# Current Auth & RBAC Assessment (pre-PHASE 10.5)

Assessment captured before implementation on 2026-08-30.

## Existing controls

- Authentication uses short-lived JWT access tokens plus refresh tokens. `get_current_user` resolves the token subject on every protected request and rejects missing, inactive, or invalid users.
- The persisted role enum is `ADMIN`, `MANAGER`, `INBOUND`, `OUTBOUND`, `WAREHOUSE`, and `VIEWER`.
- Administration endpoints require `ADMIN`; warehouse and outbound mutations use two reusable role dependencies.
- `GET /users/me` exposes identity and role, but no normalized permission or data-scope information.

## Gaps and leak paths

- There is no persisted warehouse or customer assignment for a user. All authenticated users can currently read every warehouse/customer and every operational record.
- List filters are request filters only; they do not form a mandatory authorization predicate. Counts and workbench summaries therefore reflect global data.
- Detail, allocation, transaction, event-history, export, and related-record endpoints load objects by primary key without an inherited parent-scope check.
- Global search independently queries every indexed entity and can leak exact, prefix, and contains matches, status, warehouse, customer, and target identifiers.
- Work orders, loads, operational exceptions, picking lists, and BOLs inherit business scope from their own warehouse/customer fields or parent outbound, but this inheritance is not enforced.
- Write authorization is role-only. A permitted writer can submit or mutate an object for any warehouse/customer, including attaching an outbound from another warehouse to a load.
- Master-data warehouse/customer/location selectors return global options, enabling discovery and invalid cross-scope submissions.
- Container tracking has an optional warehouse relationship and no customer foreign key. Customer enforcement is impossible for rows without a real customer relationship and must not be inferred from free text.

## PHASE 10.5 policy direction

- Keep the existing roles for backward compatibility and add explicit, reusable permissions derived from them.
- Persist independent `ALL`/`SELECTED` warehouse and customer scope modes and selected-ID mappings.
- Administrators always have effective `ALL` scope. Existing users migrate to `ALL` to preserve deployed behavior; administrators can narrow non-admin users explicitly.
- Apply mandatory scope predicates before pagination, aggregation, search ranking, or serialization. Hidden detail resources return `404` to avoid existence disclosure.
- Validate both role permission and effective data scope for every mutation and related-record attachment.
