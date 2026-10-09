# Phase 12.1B — Company Profile Singleton and Audit Coverage

## Scope

This phase changes only the FastAPI company-profile implementation, its schema migration, tests, and this document. It does not change frontend or Java behavior.

## Contract

- `GET /api/v1/company-profile` is read-only. It returns `404` when the singleton has not been initialized and `409` when legacy data contains multiple rows.
- `PUT /api/v1/company-profile` remains the sole write route and remains admin-only. With no row it creates the singleton; otherwise it updates that row.
- A no-op PUT neither commits nor creates an audit row.
- Create writes a `CREATE / COMPANY_PROFILE` audit containing the resulting profile fields.
- Update writes an `UPDATE / COMPANY_PROFILE` audit containing only fields whose values changed.
- Audit creation and profile mutation share one transaction. Audit or commit failure rolls back the profile mutation.
- Uniqueness races return `409` after rollback.

## Database invariant

Migration `20260902_0026` adds a non-null `singleton_key` fixed to `1`, protected by both a check constraint and a unique constraint. It refuses to run if legacy data contains multiple rows; operators must resolve that anomaly explicitly. It never silently deletes or merges profiles.

The migration's only parent is merge revision `20260902_0025`. Downgrade removes only the two new constraints and the new column.

## Verification status

Source and automated test verification may pass without applying the migration to a database. Until the migration is exercised against a safe database, the phase result remains `PARTIAL`.
