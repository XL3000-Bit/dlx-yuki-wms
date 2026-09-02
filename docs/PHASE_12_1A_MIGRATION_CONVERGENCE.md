# Phase 12.1A — Migration convergence and write ownership

## Decision

```text
DB_WRITE_OWNER   = FASTAPI
JAVA_API_V2_MODE = READ_ONLY
DUAL_WRITE       = PROHIBITED
```

FastAPI remains the sole database write owner. Java API v2 is an independently
verified read path and must not create, update, delete, migrate, or seed data.
Phase 12.1A changes migration metadata only; it does not apply a migration to a
database.

## Alembic graph before convergence

The nearest common ancestor is `20260830_0020`:

```text
20260830_0020
├── 20260830_0021
│   └── 20260830_0022
│       └── 20260830_0023
│           └── 20260831_0024  (head)
└── 20260901_0021              (head)
```

The live local database reported `20260830_0023` and `20260901_0021`. It has not
yet applied `20260831_0024`. No database state was changed during this phase.

### Branch inspection

| Revision | Parent | Schema/data effect |
| --- | --- | --- |
| `20260830_0021` | `20260830_0020` | Aligns defaults on `operational_exceptions.created_at` and `updated_at`. |
| `20260830_0022` | `20260830_0021` | Creates scan session/event tables, indexes, and an append-only trigger/function. |
| `20260830_0023` | `20260830_0022` | Adds picking scan columns, foreign keys, indexes, and check constraints. |
| `20260831_0024` | `20260830_0023` | Creates staging and load-verification transaction tables and indexes. |
| `20260901_0021` | `20260830_0020` | Conditionally creates `company_profiles` and conditionally seeds its singleton row. |

The branches do not alter the same tables, constraints, indexes, functions, or
seed records after their common ancestor. Neither declares a branch label or a
cross-branch dependency. The company-profile revision contains a data write; the
other branch contains DDL, constraint replacement, and trigger installation.
Those operations are appropriate for a once-only ordered migration but must not
be treated as generally idempotent. Downgrades drop schema objects and are
destructive.

## Converged graph

The empty merge revision `20260902_0025` has both former heads as parents:

```text
20260831_0024 ─┐
               ├── 20260902_0025  (head)
20260901_0021 ─┘
```

Its `upgrade()` and `downgrade()` contain no DDL or DML. Applying the merged head
later will still apply every unapplied parent migration before recording the
merge revision.

## Database write-owner inventory

### FastAPI / Python

FastAPI owns production mutations and their transactions. The current write
surface includes:

- FBA, outbound, inbound, inventory, loads, work orders, picking/BOL, scan
  execution, operational exceptions, notifications, documents, imports,
  container tracking, master data, users, and company profile mutations.
- SQLAlchemy session lifecycle through `add`, `delete`, `flush`, `commit`, and
  `rollback` in endpoints and services.
- Inventory allocation/release and movement transaction records.
- Audit-log writes for company profile and operational mutations.
- Alembic schema and seed-data ownership.

Read-only exports implemented as POST are not database write ownership merely
because of their HTTP verb; their implementations must remain free of DML.

### Java API v2

The v2 controllers expose GET-only health, master-data, and reporting routes.
Their services use read-only transactions, and the MyBatis mapper contains only
`SELECT` statements. Flyway is disabled. The configured Hikari data source is
read-only and initializes sessions with:

```sql
SET default_transaction_read_only = on
```

There is nevertheless an enforcement gap: v1 and v2 packages currently share a
Spring application and data source, and the database credential may itself be
write-capable. The connection-level guard therefore also prevents Java v1
writers in that JVM, while removal of the guard could expose v2 to accidental
writes. Before shadow verification, v2 should use a dedicated least-privilege
PostgreSQL read-only role or an equivalently isolated read-only data source.

## Phase 12.1B controlled application procedure

Do not execute this procedure as part of Phase 12.1A.

1. Schedule a maintenance window and stop application writers.
2. Take a PostgreSQL backup and prove it can be restored into a disposable
   database before touching the operational database.
3. Confirm the target URL, database name, role, and current Alembic revisions;
   expect `20260830_0023` and `20260901_0021` for the currently observed local
   database.
4. Inspect locks and long transactions, then run Alembic upgrade to
   `20260902_0025` from the controlled Python migration environment.
5. Verify that `20260831_0024` created only the expected staging/load-verification
   objects and that Alembic reports the single merged head `20260902_0025`.
6. Restart services and run authenticated read smoke tests before re-enabling
   FastAPI writes.
7. Run v1/v2 shadow-read comparison only with Java v2 using its read-only
   credential; do not route production writes to Java.

Rollback is restore-first: do not downgrade the operational database to undo a
failed application. The merge revision itself is bookkeeping-only, but reverting
through `20260831_0024` drops tables and data. Restore the verified backup if
schema or data rollback is required, then investigate offline.

## Phase result

```text
MIGRATION_GRAPH_ANALYZED = PASS
EMPTY_MERGE_SAFE         = PASS
DATABASE_MIGRATED        = NO
DB_WRITE_OWNER           = FASTAPI
JAVA_API_V2_MODE         = READ_ONLY
SHADOW_READ_VERIFY       = NOT STARTED
```
