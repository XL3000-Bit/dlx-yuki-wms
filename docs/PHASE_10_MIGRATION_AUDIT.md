# PHASE 10 Migration Audit

Audit date: 2026-08-30. Release status: **PASS FOR RC**.

## Chain

Alembic reports one linear head, `20260830_0021`. Phase 10 revisions are `0013` Load, `0014` Work Order, `0015` Work Order Events, `0016` generic event fields, `0017` operational exceptions, `0018` scoped RBAC, `0019` operational documents, `0020` operational notifications, and `0021` Phase 10.9 RC schema alignment.

Revision `0021` aligns `operational_exceptions.created_at` and `updated_at` with the application's timestamp mixin by adding PostgreSQL server defaults while retaining NOT NULL. This removes the PostgreSQL-only exception-creation blocker without changing routes or business state rules.

Revisions `0019` and `0020` each use a single explicit PostgreSQL enum lifecycle. Their table declarations reference existing enum types instead of attempting duplicate type creation.

## Execution evidence

- `alembic heads`: PASS, one head (`20260830_0021`).
- Empty isolated PostgreSQL schema `alembic upgrade head`: PASS.
- Empty isolated schema `alembic check`: PASS, no drift.
- Isolated PostgreSQL `20260828_0012 -> head`: PASS.
- `0021 -> downgrade 0020 -> upgrade 0021`: PASS.
- At head, `operational_exceptions.created_at` and `updated_at` are NOT NULL and have `now()` defaults.
- The production service path created an Operational Exception with non-null timestamps and its immutable creation event.
- All temporary schemas created for this audit were removed.

## Development database drift recovery

The local `public` schema reported revision `0020` while its Phase 10 tables were absent. The only Phase 10 residue was `outbound_orders.load_id`; all values were NULL.

After read-only assertions confirmed that revision, absence of every Phase 10 table, and an entirely empty orphan column, only the orphan index/column was removed. The version was stamped back to `20260828_0012`, then the standard `alembic upgrade head` replayed `0013` through `0021`. No outbound order was deleted. Final `alembic current` and `alembic check` both pass.

## PostgreSQL compatibility conclusion

PostgreSQL is verified through head for fresh install, upgrade from the Phase 9.5 boundary, head schema comparison, exception insertion, and the latest revision's downgrade/re-upgrade cycle. Static review also covered foreign keys, indexes, enum teardown order, timezone-aware timestamps, server defaults, unique constraints, JSON payloads, and transactional rollback.

The application role still lacks `CREATEDB`; safe isolated schemas in the configured database were used instead. This is an environment limitation, not an RC blocker.
