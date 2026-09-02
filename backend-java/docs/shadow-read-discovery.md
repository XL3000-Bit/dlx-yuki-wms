# Shadow read discovery

Discovery date: 2026-09-02 (America/Los_Angeles)
Repository HEAD: `cefe1a23b9779b71ce9c7097b0fdf020a14bca6d`

## Safety state at entry

- The working tree was already dirty in Java, Python, frontend, PDA, 3PL, and image/Nginx paths. Those changes are treated as pre-existing and are not cleaned, staged, or overwritten.
- No listener was present on ports 8000, 8081, or 5173 during discovery.
- `SHADOW_ADMIN_TOKEN`, `SHADOW_SCOPED_TOKEN`, `DATABASE_URL`, `JWT_SECRET`, and `JWT_SECRET_KEY` were not present in the invoking process environment.
- This task will not persist credentials or complete response bodies.

## Route inventory and semantic classification

| Dataset | Python v1 | Java v2 | Classification | Notes |
|---|---|---|---|---|
| Health | `GET /health` | `GET /api/v2/health` | `CONTRACT_DIFFERENCE` | Both expose service health, but service metadata differs. |
| Database health | none | `GET /api/v2/health/db` | `NO_EQUIVALENT_V1` | Java-only database reachability probe. |
| Customers | `GET /api/v1/master-data/customers` | `GET /api/v2/customers` | Comparable read set | Customer scope is applied by both implementations. |
| Warehouses | `GET /api/v1/master-data/warehouses` | `GET /api/v2/warehouses` | Comparable read set | Warehouse scope is applied by both implementations. |
| Carriers | `GET /api/v1/master-data/carriers` | `GET /api/v2/carriers` | Comparable read set | Authenticated global list in both implementations. |
| FC addresses | `GET /api/v1/master-data/amazon-fc-addresses` | `GET /api/v2/fc-addresses` | Comparable read set | Authenticated global list. Python additionally has an exact-code route. |
| Operations dashboard | `GET /api/v1/dashboard/operations` | `GET /api/v2/reporting/dashboard` | `CONTRACT_DIFFERENCE` | v1 is date-aware; v2 is a three-section aggregate without date parameters. |

Java v2 master-data routes do not expose pagination, search, or sorting parameters. Such matrices are unsupported, not equivalent. Python's exact FC-code lookup has no Java v2 equivalent.

## Authentication and scope

- Both sides accept `Authorization: Bearer <JWT>` and use numeric `sub` to load the active user.
- Java v2 returns FastAPI-compatible `detail` envelopes for missing and invalid credentials.
- Java `ReadScope` treats admin or `ALL` as unrestricted and otherwise reads IDs from `user_warehouses` and `user_customers`.
- Customers and warehouses are scoped; carriers and FC addresses are authenticated global lists, matching inspected Python routes.
- Admin, scoped, nonexistent, and disabled-user runtime checks require safe external tokens. None was available during discovery.

## Read-only controls

- `spring.flyway.enabled=false`.
- Hikari uses `readOnly=true` and `SET default_transaction_read_only = on`.
- Java v2 services use `@Transactional(readOnly=true)`.
- Inspected v2 mapper XML contains SELECT statements only.
- Runtime database identity, least-privilege grants, same-datasource identity, before/after counts, and write rejection remain unproved.

## Execution gate

Runtime comparison requires both services, safe admin/scoped JWTs, and proof that both runtimes use the same designated datasource. Otherwise the result is `BLOCKED`, not PASS.
