# DEV/TEST Database Safety Boundary

## Status and scope

The stable main database `dlx_yuki_wms` is protected. It must not be reset,
seeded, or used as a development shortcut. PDA development remains paused and
PDA production use remains prohibited.

The repository includes fail-closed migration and explicit DEV synthetic-seed
entry points. Neither operation runs during application startup or through an
API endpoint.

The database identities and responsibilities are deliberately separate:

| Database | Application role | Allowed workflow |
| --- | --- | --- |
| `dlx_yuki_wms` | Production/main credentials only | Stable main database; never used by development migration, seed, reset, or validation commands |
| `dlx_yuki_wms_dev` | `dlx_yuki_wms_dev_user` | Development migrations, deterministic synthetic seed, and explicitly confirmed schema reset/reseed |
| `dlx_yuki_wms_test` | `dlx_yuki_wms_test_user` | Test migrations and read-only verification; never reset or seeded by the DEV workflow |

The DEV and TEST roles are login roles with no `SUPERUSER`, `CREATEDB`,
`CREATEROLE`, `REPLICATION`, or `BYPASSRLS` privilege. Each role is authorized
only for its matching database. Administrative credentials are not application
credentials and must not be placed in project files or automation.

## Exact destructive-operation allowlist

| `WMS_ENV` | Only permitted database |
| --- | --- |
| `development` | `dlx_yuki_wms_dev` |
| `test` | `dlx_yuki_wms_test` |

`production` is recognized but never permits a destructive DEV/TEST operation.
Unknown or missing environments, missing or malformed URLs, cross-environment
targets, the protected main database, and every database outside this table are
refused.

This table defines targets recognized by the shared database-safety validator;
it does not authorize seeding or resetting TEST. DEV seed/reset tooling is
restricted to `development` + `dlx_yuki_wms_dev`.

The validation entry point is
`app.core.database_safety.validate_destructive_database_target`. It parses
configuration without opening a connection. The migration wrapper at
`scripts/safe_alembic.py` accepts only process-level `WMS_ENV` and
`DATABASE_URL`, verifies the connected server's `current_database()` on the
same connection Alembic uses, upgrades only through `20260902_0026`, and then
requires that exact single revision in `alembic_version`.

Set `WMS_ENV` and `DATABASE_URL` in the current process without printing either
value. From `backend`, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.safe_alembic
```

The wrapper prints only a sanitized environment/host/port/database summary.

Migration bootstrap is fail-closed. An empty allowed DEV or TEST database may
be bootstrapped only through the checked-in Alembic history, while an existing
database must match that history. Unknown, divergent, multiple-head, or
partially initialized schema states stop the workflow. Existing Alembic
migration files must not be rewritten to make a database pass validation.

## Credential handling

Errors use fixed messages and do not echo inputs. A validated target may be
reported only as environment, host, port, and database name. Do not print a
complete `DATABASE_URL`, username, password, token, secret, or `.env` content.

The files under `backend/config` contain fake example credentials only. Actual
environment files remain local and must not be copied into documentation or
source control.

## Deterministic DEV synthetic seed

From the repository root, explicitly run:

```powershell
.\backend\scripts\seed_dev.ps1
```

The visible PowerShell window asks separately for the low-privilege DEV database
role password and a DEV-only synthetic application-user password. Input is
hidden, retained only in process memory, removed from the process environment in
a `finally` block, and never written to `.env`, source control, or the sanitized
result file.

The seed command is restricted to `development` + `dlx_yuki_wms_dev`, verifies
the connected database and exact Alembic revision, accepts only the known
migration baseline, and writes the entire deterministic graph in one
transaction. A complete matching graph returns `PASS_NO_CHANGES`; partial or
unknown data stops without deletion. Synthetic natural keys use `DEV-` or
`SYN-`, and business dates are fixed to 2026-09-01 through 2026-09-03.

TEST remains a clean migration baseline and is never written by seed/reset
tools. PDA development remains paused; no PDA, tail-pallet, split-pallet,
consolidation, offline-queue, or production-PDA data is created.

## Safe DEV reset and reseed

Use the destructive workflow only for DEV and only after reviewing the target
shown by the safety checks. From the repository root, run:

```powershell
.\backend\scripts\reset_and_reseed_dev.ps1 -ConfirmDatabase dlx_yuki_wms_dev
```

The wrapper requests required credentials through hidden input. Reset proceeds
only when all three conditions agree: `WMS_ENV=development`, the connected
`current_database()` is `dlx_yuki_wms_dev`, and `-ConfirmDatabase` is exactly
`dlx_yuki_wms_dev`. Missing configuration, an unknown database, production or
test environment, the main or TEST database, and an incorrect confirmation are
rejected.

The implementation performs a controlled schema reset inside DEV; it does not
depend on `DROP DATABASE` or `CREATE DATABASE`, so the application role does not
need `CREATEDB` or `SUPERUSER`. It then runs the safe Alembic upgrade, verifies
revision `20260902_0026` and migration bootstrap, applies and verifies the
deterministic DEV seed, and runs the seed a second time to prove idempotency. It
must not connect to main or reset/reseed TEST.

## Credential and PDA policy

Store real passwords only in an approved local secret mechanism or enter them
at a hidden interactive prompt. Never commit passwords, tokens, complete
database URLs, `.pgpass`, private keys, or local `.env` contents. Examples and
diagnostics must remain sanitized. PostgreSQL authentication configuration is
outside this workflow and must not be weakened or changed to bypass
authentication.

PDA development remains paused. PDA production use is prohibited, and no PDA
action is authorized by migration, seed, reset, or validation workflows.

## Owned temporary dispatch verification (2026-10-05)

`backend/.venv/Scripts/python.exe scripts/verify_dispatch_isolated.py` creates
its own PostgreSQL cluster in TEMP on a random loopback port. It verifies the
connected data directory and test role, migrates a fresh template to 0039, then
clones an isolated database per scenario. It does not use the project's database
URL, reset DEV/TEST/main, change existing authentication, or restart existing
services. The cluster is stopped on exit and its logs/data are retained for
inspection. Requires installed PostgreSQL binaries; `YUKI_TEST_PG_BIN` can
specify their directory.

The original transaction tests use an explicitly test-only substitute; the new
evidence tests use real persisted, versioned TEST ONLY policies and reviews.
Both prove mechanisms only. Unconfigured production document, approval and
exception-review rules remain UNKNOWN and blocked. No policy configuration API
or production seed is provided. See [current evidence/browser acceptance and
remaining decisions](DISPATCH_EVIDENCE_ACCEPTANCE_2026-10-05.md).

For browser acceptance, run from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe scripts/start_dispatch_browser_isolated.py
```

This creates a separate owned TEMP cluster, validates its data directory and
role before fresh migrations, seeds synthetic cases and explicitly labeled test
policies, and starts its own API and Vite processes on random loopback ports.
The application receives process-local configuration; project credentials and
existing services are untouched. Runtime application modules do not import the
test-policy helpers. Read the printed resource directory and local browser URL.
To stop, write a `stop` file in that exact returned owned directory:

```powershell
Set-Content -LiteralPath '<returned owned TEMP directory>\stop' -Value stop
```

The runner finally stops only its child processes and owned PostgreSQL cluster,
retaining logs/data. `--resume <owned TEMP directory>` validates the ownership
marker, TEMP path and PostgreSQL data, and resumes without reseeding. This is a
test-resource lifecycle operation, not permission to start or change production.
