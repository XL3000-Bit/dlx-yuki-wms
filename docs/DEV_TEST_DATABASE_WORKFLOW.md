# DEV/TEST Database Safety Boundary

## Status and scope

The stable main database `dlx_yuki_wms` is protected. It must not be reset,
seeded, or used as a development shortcut. PDA development remains paused and
PDA production use remains prohibited.

The repository includes fail-closed migration and explicit DEV synthetic-seed
entry points. Neither operation runs during application startup or through an
API endpoint.

## Exact destructive-operation allowlist

| `WMS_ENV` | Only permitted database |
| --- | --- |
| `development` | `dlx_yuki_wms_dev` |
| `test` | `dlx_yuki_wms_test` |

`production` is recognized but never permits a destructive DEV/TEST operation.
Unknown or missing environments, missing or malformed URLs, cross-environment
targets, the protected main database, and every database outside this table are
refused.

The validation entry point is
`app.core.database_safety.validate_destructive_database_target`. It parses
configuration without opening a connection. The migration wrapper at
`scripts/safe_alembic.py` accepts only process-level `WMS_ENV` and
`DATABASE_URL`, verifies the connected server's `current_database()` on the
same connection Alembic uses, upgrades only through `20260902_0026`, and then
requires that exact single revision in `alembic_version`.

From `backend`, set the two variables explicitly and run:

```powershell
.\.venv\Scripts\python.exe -m scripts.safe_alembic
```

The wrapper prints only a sanitized environment/host/port/database summary.

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
