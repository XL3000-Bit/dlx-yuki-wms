# Java `/api/v2` shadow read verification

Verification date: 2026-09-02 (America/Los_Angeles)
Repository HEAD: `cefe1a23b9779b71ce9c7097b0fdf020a14bca6d`

## Scope and result

This run exercised Java directly on `127.0.0.1:8081`. It did not route traffic
through Nginx, modify Python `/api/v1`, change frontend routing, or use the retained
verification worktree at `C:\Users\XL\dlx-yuki-wms-v2-verify`.

No safe test database identity or test JWT source was configured in the process
environment. A PostgreSQL listener was present on local port 5432, but its database,
role permissions, and production status were unknown, so it was deliberately not
contacted. In accordance with the safety gate, database reads and v1/v2 data
comparison were skipped.

```text
SHADOW_JWT          = FAIL
SHADOW_DB_READONLY  = SKIPPED_NO_SAFE_DB
SHADOW_V1_V2_MATCH  = PARTIAL
SHADOW_NGINX_LIVE   = NOT_STARTED
SHADOW_READ_VERIFY  = PARTIAL
```

`SHADOW_JWT = FAIL` means Python-token interoperability was not proven in this run;
it does not mean a Python token was tested and rejected. The HTTP authentication
envelope passed: anonymous health returned 200, while missing and malformed bearer
tokens returned compatible `detail` 401 responses. A real Python access token was
not available and Java did not issue a substitute token.

## Configuration review

- Default Java port: `8081` (`YUKI_SERVER_PORT`, then `PORT`, then 8081).
- Context path: `/`; v2 controllers declare their complete `/api/v2` paths.
- JWT secret: `YUKI_JWT_SECRET`, with `JWT_SECRET_KEY` as the Python-compatible
  fallback. Algorithm setting: `JWT_ALGORITHM`, default `HS256`.
- Python token claims expected by the Java filter: numeric string `sub`,
  `type=access`, plus the normal `iat`, `exp`, and `jti` claims.
- `spring.flyway.enabled=false`.
- The Hikari data source sets `readOnly=true` and initializes connections with
  `SET default_transaction_read_only = on`.
- The v2 read services use read-only transactions.

## Direct 8081 startup and HTTP checks

Java started successfully on port 8081 with an explicit, intentionally unreachable
database URL on `127.0.0.1:65432`. This allowed the web and JWT boundary to be checked
without connecting to the unknown PostgreSQL listener on port 5432. The process was
stopped after these checks.

| Request | Token | Actual result | Result |
|---|---|---|---|
| `GET http://127.0.0.1:8081/api/v2/health` | none | 200, `{"service":"yuki-wms-java","status":"ok","mode":"read-only"}` | PASS |
| `GET http://127.0.0.1:8081/api/v2/customers` | none | 401, `{"detail":"Not authenticated"}` | PASS |
| `GET http://127.0.0.1:8081/api/v2/customers` | malformed bearer value | 401, `{"detail":"Invalid credentials"}` | PASS |
| protected v2 read | Python-issued test access token | Not run: no test login/token configuration | FAIL (not proven) |
| `GET http://127.0.0.1:8081/api/v2/health/db` | none | Not run against a database | SKIPPED_NO_SAFE_DB |

No token, password, cookie, or real database credential is recorded in this file.

## Read-only database identity

No existing role could be established as a safe test-only, read-only identity, so no
database command was executed. A human may run the following example only against a
designated test/development database, replacing every placeholder and limiting the
grants further if the test schema permits it:

```sql
-- Example only. Codex did not execute this against any database.
CREATE ROLE yuki_wms_readonly LOGIN PASSWORD '<supply-outside-source-control>';
GRANT CONNECT ON DATABASE <test_database> TO yuki_wms_readonly;
GRANT USAGE ON SCHEMA public TO yuki_wms_readonly;
GRANT SELECT ON TABLE
  customers,
  warehouses,
  carriers,
  amazon_fc_addresses,
  inbound_records,
  inventory_lots,
  outbound_orders
TO yuki_wms_readonly;
```

Before repeating this gate, manually confirm with that test role that a representative
`SELECT` succeeds and an `INSERT` or `UPDATE` fails. Do not add the write probe to the
application and do not perform it with a production identity.

## Python v1 / Java v2 comparison

All data comparisons require the same safe database and the same Python-issued test
access token. Neither was available, so no row counts, field parity, dashboard values,
or authorization scope can be asserted. In particular, absence of a comparison is not
evidence that v2 scope is equal to or narrower than v1.

| Data set | Python v1 URL | Java v2 URL | HTTP status | Key fields / count / scope | Classification |
|---|---|---|---|---|---|
| Customers | `http://127.0.0.1:8000/api/v1/master-data/customers` | `http://127.0.0.1:8081/api/v2/customers` | Not run | `id`, name/code, count, customer scope not compared | SKIPPED |
| Warehouses | `http://127.0.0.1:8000/api/v1/master-data/warehouses` | `http://127.0.0.1:8081/api/v2/warehouses` | Not run | `id`, name/code, count, warehouse scope not compared | SKIPPED |
| Carriers | `http://127.0.0.1:8000/api/v1/master-data/carriers` | `http://127.0.0.1:8081/api/v2/carriers` | Not run | `id`, name/code and count not compared | SKIPPED |
| FC addresses | `http://127.0.0.1:8000/api/v1/master-data/amazon-fc-addresses` | `http://127.0.0.1:8081/api/v2/fc-addresses` | Not run | `id`, FC name/code and count not compared | SKIPPED |
| Dashboard | `http://127.0.0.1:8000/api/v1/dashboard/operations` | `http://127.0.0.1:8081/api/v2/reporting/dashboard` | Not run | inbound, inventory, outbound totals and user scope not compared | SKIPPED |

The dashboard endpoints are recorded as the routes implemented by each application;
their response semantics still require runtime comparison and must not be assumed to
match from their names alone.

## Module test gate

`mvn -q test` completed successfully in the original `backend-java` module:

```text
Test suites: 48
Tests:       112
Failures:    0
Errors:      0
Skipped:     0
```

This includes `com.yuki.wms.v2.V2WebContractTest` and
`com.yuki.wms.v2.ReportingReadMapperContractTest`, as well as the existing FBA
allocation/release contract coverage. It verifies the Spring context and mapper XML
binding without authorizing a connection to an unknown database.

## FBA byte-preservation check

The opening SHA-256 values were:

| File | Opening SHA-256 | Closing SHA-256 | Result |
|---|---|---|---|
| `FbaController.java` | `B5CEA4D758A9F1027C1E2CCB70A0513B6B522590C98F915EF3627D7E36AA61D0` | `B5CEA4D758A9F1027C1E2CCB70A0513B6B522590C98F915EF3627D7E36AA61D0` | SAME |
| `FbaService.java` | `FF077DE91DE9C352F679855D681EFC17B258B8DAD229F06D46BEED71E4325A93` | `FF077DE91DE9C352F679855D681EFC17B258B8DAD229F06D46BEED71E4325A93` | SAME |
| `FbaRepository.java` | `8A39C02C33204715E53A4D811B3CF54DBF97DB24316C5081B9980ED8F6A846D7` | `8A39C02C33204715E53A4D811B3CF54DBF97DB24316C5081B9980ED8F6A846D7` | SAME |

All three files were byte-identical across this task.

## Nginx status and rollback boundary

No live Nginx configuration was read, changed, or reloaded.

1. Shadow verification first accesses only `127.0.0.1:8081`.
2. If a future task enables an `/api/v2` upstream, deleting or commenting that
   location is the rollback.
3. `/api/v1` must continue to point to FastAPI.

## Remaining work for a PASS

- Provision or identify a test-only PostgreSQL database role whose grants are proven
  read-only.
- Start Python `/api/v1` against that same test database and obtain a test user's
  Python-issued access token without persisting it.
- Prove the token accesses all protected Java endpoints.
- Execute all five v1/v2 comparisons, including counts, key-field mapping, dashboard
  figures, and user customer/warehouse scope; any `SCOPE_WIDER` is a failure.

No frontend cutover, live Nginx split, Outbound migration, PDA work, 3PL work, or new
FBA write work was started in this verification.
