# PHASE 10 Migration Audit

Audit date: 2026-08-30. Release status: **blocked**.

## Chain

Alembic reports one head, `20260830_0020`. The Phase 10 revisions form a linear chain: `0013` Load, `0014` Work Order, `0015` Work Order Events, `0016` generic event fields, `0017` operational exceptions, `0018` scoped RBAC, `0019` operational documents, and `0020` operational notifications. The configured development PostgreSQL database is currently at `20260828_0012`.

The revisions were statically reviewed for `down_revision`, named constraints/indexes, foreign keys, enum lifecycle, and downgrade operations. The chain has no branch or duplicate head. Foreign keys and supporting indexes exist for the principal ownership, entity, status, warehouse, unread-notification, and dedupe access paths. Downgrades remove tables/indexes before enum types.

## Execution evidence

- `alembic heads`: PASS, one head (`20260830_0020`).
- `alembic history`: PASS, linear history.
- `alembic current`: development PostgreSQL is `20260828_0012`.
- Empty PostgreSQL schema `alembic upgrade head`: **FAIL** at `20260830_0020`; the corrected `0019` completes successfully first.
- Isolated PostgreSQL schema `20260828_0012 -> head`: `0012` succeeds, then **FAIL** at `0020`.
- `0019 -> downgrade 0018 -> upgrade 0019`: PASS. Both dependent tables are removed before the two enum types; post-downgrade table and enum counts are zero, and re-upgrade restores both counts to two.
- Isolated schema cleanup: PASS for `phase109_fresh`, the upgrade-path schema, and the lifecycle schema.
- A separate empty database could not be created because the application role lacks `CREATE DATABASE`/`CREATEDB`.

## Blocking defect

The authorized correction to `20260830_0019_operational_documents.py` uses PostgreSQL `ENUM(..., create_type=False)` for `operational_document_type` and `operational_document_status`, while retaining the single explicit `create(checkfirst=True)` lifecycle. The final schema and downgrade order are unchanged. Fresh PostgreSQL execution and the isolated up/down/up smoke confirm the correction.

Inspection and execution then found the same defect in `20260830_0020_operational_notifications.py`: it explicitly creates `notification_type` and `notification_severity`, and table creation attempts to create `notification_type` again. PostgreSQL raises `psycopg.errors.DuplicateObject`. The task authorization was limited to `0019`, so `0020` was not modified. This remains a Critical release blocker.

## PostgreSQL compatibility review

PostgreSQL was reachable and the failure above was reproduced against it. Static review covered enum creation/drop ordering, timezone-aware timestamps, booleans/server defaults, unique constraints, `ILIKE`, JSON payloads, foreign keys, and transactional rollback. Application tests predominantly use SQLite, so they do not exercise PostgreSQL enum DDL or all dialect semantics.

**POSTGRESQL NOT VERIFIED TO HEAD**: PostgreSQL isolated-schema testing is available and `0019` is verified, but `0020` prevents the chain from reaching head. The role still cannot create a separate database.
