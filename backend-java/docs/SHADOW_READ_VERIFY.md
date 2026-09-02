# SHADOW READ VERIFY

Run date: 2026-09-02 (America/Los_Angeles)
Repository HEAD: `cefe1a23b9779b71ce9c7097b0fdf020a14bca6d`

## Conclusion

`SHADOW_READ_VERIFY = BLOCKED`

This run cannot establish v1/v2 parity. Neither service was reachable, safe admin and scoped JWTs were not supplied, and the two runtimes were not proven to use the same designated datasource. The local shell also has neither `java` nor `mvn` available on `PATH`, so the required clean build gates could not run.

`PDA_CAMERA_SCAN = PARTIAL` remains unchanged. No PDA work was started.

## Build gates

| Gate | Result | Evidence |
|---|---|---|
| `mvn -q clean test` | BLOCKED / not run | `mvn` is not installed or not available on `PATH`; no Maven wrapper exists in `backend-java`. |
| `mvn -q clean package` | BLOCKED / not run | Same Maven prerequisite blocker. |

No prior build result is reused as evidence for this run.

## Runtime comparison

The repeatable runner wrote `build/shadow-read/shadow-read-summary.json` with result `BLOCKED` and 15 planned cases.

| Area | Result |
|---|---|
| v1 base `http://127.0.0.1:8000` | Unreachable |
| v2 base `http://127.0.0.1:8081` | Unreachable |
| Safe admin token | Not supplied |
| Safe scoped token | Not supplied |
| Same datasource proof | Not supplied |
| Public health checks | Not executed successfully |
| Missing/malformed-token checks | Not executed successfully because services were unreachable |
| Admin/scoped dataset comparisons | Not executed; no safe credentials |
| Nonexistent/disabled-user checks | Not executed; no safe credentials |

No response bodies or credentials were persisted.

## Route classification

Comparable read sets discovered statically:

- customers: v1 `/api/v1/master-data/customers`, v2 `/api/v2/customers`
- warehouses: v1 `/api/v1/master-data/warehouses`, v2 `/api/v2/warehouses`
- carriers: v1 `/api/v1/master-data/carriers`, v2 `/api/v2/carriers`
- FC addresses: v1 `/api/v1/master-data/amazon-fc-addresses`, v2 `/api/v2/fc-addresses`

Explicit differences:

- health endpoints are `CONTRACT_DIFFERENCE` because their metadata and paths differ.
- v2 `/api/v2/health/db` is `NO_EQUIVALENT_V1`.
- dashboard endpoints are `CONTRACT_DIFFERENCE`: v1 operations dashboard is date-aware and structurally richer; v2 reporting dashboard is a three-section aggregate.
- v1 exact FC-code lookup has no Java v2 equivalent.
- Java v2 master lists expose no matching pagination/search/sort contract, so those parameter matrices are not treated as parity cases.

## Read-only evidence

Static controls found:

- Flyway is disabled.
- Hikari is configured read-only and initializes sessions with `SET default_transaction_read_only = on`.
- inspected v2 services use read-only transactions.
- inspected v2 mapper XML contains SELECT statements only.

Runtime proof is incomplete:

- database identity and grants were not queried;
- write rejection was not tested;
- before/after table counts were not captured;
- database-account least privilege cannot be classified.

Therefore `DB_ACCOUNT_NOT_LEAST_PRIVILEGE` is not asserted or cleared; it remains unverified.

## Files created or changed by this task

- `backend-java/.gitignore` — ignores generated shadow-read output only.
- `backend-java/docs/shadow-read-discovery.md`
- `backend-java/docs/SHADOW_READ_VERIFY.md`
- `backend-java/tools/shadow-read/shadow_read.py`
- generated, ignored: `backend-java/build/shadow-read/shadow-read-summary.json`

The working tree already contained unrelated Java, Python, frontend, PDA, 3PL, image, and Nginx changes. They were preserved and were not staged, committed, reset, stashed, cleaned, or overwritten.

## Requirements to unblock

1. Make Java 21 and Maven available in the task shell.
2. Start the designated v1 and v2 builds on 8000 and 8081.
3. Provide safe admin and scoped JWTs through `SHADOW_ADMIN_TOKEN` and `SHADOW_SCOPED_TOKEN`.
4. Confirm both runtimes point to the same designated read-only datasource with `SHADOW_SAME_DATASOURCE_VERIFIED=true`.
5. Re-run both clean Maven gates, then run `tools/shadow-read/shadow_read.py` and collect runtime scope, auth, shape, count, and read-only evidence.

No Java/Python business logic, FBA code, schema, frontend routing, proxy, Nginx, or production data was changed.
