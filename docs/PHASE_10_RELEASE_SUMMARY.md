# PHASE 10 Release Candidate Summary

Status: **NOT READY FOR RC** (2026-08-30).

## Architecture and features

Phase 10 extends the existing FastAPI/SQLAlchemy/Alembic backend and React/TypeScript frontend with Global Search, Load Management, Warehouse Work Orders and immutable events, Trouble Shoot exceptions, scoped RBAC, an Operations Dashboard, Document/POD storage, and operational notifications. It does not add a new business domain in Phase 10.9.

APIs remain under `/api/v1`; the production frontend uses the same-origin base and does not depend on the Vite development proxy. Route pages use `React.lazy`. Search covers Container, Outbound, FBA, Picking, BOL, Load, Work Order, Exception, and Document with bounded result collection, ranking/deduplication, scoped queries, and deep links.

## Security and consistency audit

The automated matrix covers Admin/Manager/Operator/Viewer and cross-warehouse access across scoped lists/details, search, dashboard counts, events, documents/downloads, notifications, lookups, and mutations. Forty focused tests passed. Static endpoint review found no update/delete route for Work Order, Exception, or Document events. Event creation is transaction-coupled to valid operations.

API paths, enum/datetime serialization, pagination, and error policies were reviewed. No low-risk API rewrite was justified. Cross-module query-state/deep-link code was reviewed, but browser refresh behavior still requires the manual checklist.

## Performance, indexes, and bundle

List/detail services use eager loading or bounded queries; dashboard aggregation is database-side and search has per-entity caps. No evidenced N+1 warranted a release-time refactor. Existing Phase 10 migrations include indexes for operational status/ownership/warehouse/date identifiers and notification user/read/dedupe paths; no new migration was added.

The production build transforms 5,015 modules. Route chunks are lazy-loaded; the main app chunk is 248.31 kB (81.96 kB gzip). The Ant Design vendor chunk remains 1,168.79 kB (364.42 kB gzip), producing the known 500 kB warning. A build-system redesign was intentionally deferred.

## Storage, notifications, and operations

Document storage has a configurable root and upload limit, path traversal protection, bounded streaming, failed-write cleanup, access checks, versioning, and archive semantics. Runtime storage and generated pytest directories are ignored; `.env.example` documents the settings. Local filesystem storage remains unsuitable for horizontally scaled production without shared durable storage. There is no malware scan.

Notifications implement recipient scope, read/mark-all, refresh, inactive handling, dedupe keys, and deep links. Repeated refresh behavior has automated coverage. Generation is request-driven; there is no scheduler. Existing backup/restore scripts use full-database `pg_dump`/`pg_restore`, so Phase 10 tables are naturally included.

## Tests and release configuration

Backend: 119 passed with one pytest cache permission warning; the focused security matrix passed 40/40. Frontend: production build passed with the Ant Design chunk warning. Configuration uses debug off by default, explicit CORS, JWT settings, PostgreSQL URL, business timezone, backup path, and document settings; no secret was added. Critical paths were checked for accidental logging of passwords, tokens, cookies, authorization headers, or file contents; no new logging framework was introduced.

## Known limitations

- Resolved in scope: migration `0019` now has one PostgreSQL enum lifecycle; fresh execution and up/down/up validation pass without orphan enums.
- Blocking: migration `0020` has the same duplicate enum lifecycle for `notification_type`; fresh-schema and `0012 -> head` validation cannot reach head.
- The local role cannot create a separate empty database; safe isolated PostgreSQL schemas were used and cleaned successfully.
- Manual browser smoke is pending.
- Document storage is local, has no malware scan, and needs operational backup/retention policy.
- Notifications have no background scheduler; customer scope remains limited to implemented mappings.
- Container/POD-specific alert and SLA rules are not implemented.
- Ant Design vendor chunk remains above 500 kB.
- The working tree contains user-owned deleted tracked pytest XLSX fixtures; they were not restored or removed.

See `PHASE_10_MIGRATION_AUDIT.md`, `PHASE_10_TEST_REPORT.md`, and `PHASE_10_MANUAL_SMOKE_CHECKLIST.md` for evidence and follow-up.
