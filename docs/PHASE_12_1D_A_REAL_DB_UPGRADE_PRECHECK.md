# PHASE 12.1D-A — Real Database Read-Only Precheck, Backup, and Clone Rehearsal

## Final status

```text
PHASE_12_1D_A            = READY_FOR_PHASE_12_1D_B
REAL_WMS_DATABASE        = UNCHANGED
REAL_DATABASE_UPGRADE    = NOT_EXECUTED
BACKUP                   = VERIFIED_AND_RETAINED
CLONE_RESTORE            = PASS
CLONE_MIGRATION          = PASS
CLONE_CLEANUP            = PASS
SETTINGS_FRONTEND        = PAUSED
```

This phase performed read-only inspection and backup against the real WMS database. All restore, migration, constraint, and API write checks were executed only against a disposable PostgreSQL clone. It did not run Alembic upgrade, schema DDL, or application writes against the real database.

## 1. Source and workspace baseline

- Repository: `C:\Users\XL\dlx-yuki-wms`
- Source revision: `cefe1a23b9779b71ce9c7097b0fdf020a14bca6d`
- Staged diff at entry: empty
- The pre-existing dirty working tree was recorded and preserved. It included ongoing Java, Python, frontend, documentation, image, and Nginx work outside this phase.
- This report is the only persistent file added by PHASE 12.1D-A.
- No file was staged, committed, pushed, stashed, reset, or cleaned.

## 2. Migration graph and source integrity

Validated graph:

```text
20260830_0023 -> 20260831_0024 --+
                                      +-> 20260902_0025 -> 20260902_0026
20260901_0021 --------------------+
```

Alembic source head is `20260902_0026`.

| Migration | SHA-256 |
|---|---|
| `20260902_0025_merge_heads.py` | `738255CF6804D40C0C946FA942565F6DD49C4711F4BBF886071D2FA068D64525` |
| `20260902_0026_company_profile_singleton.py` | `1B9D1C20187F12C958B665A40741074C270E7A8984158F3D856D61306311CE9B` |

Neither migration was modified during this phase.

## 3. Tooling safety gate

- Docker Client and Server: `29.7.2`, accessible
- PostgreSQL dump/restore tools: `17.11`
- Real PostgreSQL server: `17.11`
- No current application `DATABASE_URL` was reused for the disposable clone.
- The clone used a randomized container name, database name, host port, and password.
- No existing Docker volume was mounted.

## 4. Real database read-only precheck

Read-only identity and state:

```text
database             = dlx_yuki_wms
user                 = dlx_user
client_address       = ::1/128
port                 = 5432
server               = PostgreSQL 17.11 on Windows
in_recovery           = false
schema               = public
database_size_bytes  = 127858355
table_count           = 39
revisions             = 20260830_0023, 20260901_0021
company_profile_rows = 1
company_profile_ids  = 1
singleton_key_column = absent
```

The revision gate matched the required two-head state exactly, and the Company Profile row-count gate passed.

Captured real table counts:

```text
alembic_version=2
amazon_fc_addresses=0
audit_logs=1921
bol_items=9
bols=5
carriers=0
company_profiles=1
container_trackings=1
customers=0
document_events=8
fba_inventory_allocations=93
fba_shipments=93
import_errors=99324
import_jobs=11
import_rows=37331
inbound_records=633
inventory_lot_locations=521
inventory_lots=626
inventory_priority_rules=4
inventory_transactions=738
loads=1
operational_documents=4
operational_exception_events=7
operational_exceptions=2
operational_notifications=1
outbound_inventory_allocations=12
outbound_orders=24
picking_list_items=4
picking_lists=15
scan_events=0
scan_sessions=0
user_customer_scopes=0
user_warehouse_scopes=0
users=1
warehouse_areas=1
warehouse_locations=282
warehouses=1
work_order_events=4
work_orders=1
```

## 5. Retained pre-upgrade backup

The backup is outside the repository and is intentionally retained for the controlled upgrade phase.

```text
file   = C:\Users\XL\dlx-yuki-wms-private-backups\phase_12_1d\20260902_111707\dlx_yuki_wms_preupgrade.dump
size   = 7,928,090 bytes
sha256 = ADCF20FB7A2D83094912F9EF77458DD366E6EFD9EA88EA50CD8B4652E10B61EF
format = PostgreSQL custom dump
```

`pg_restore --list` succeeded and produced 2,399 lines. The list is retained beside the dump as `pg_restore_list.txt`.

## 6. Disposable clone restore and parity

Clone isolation identifiers (password omitted):

```text
container = wms_12_1d_clone_1788373082453_349822
database  = dlx_yuki_wms_clone_rehearsal_1788373082453_349822
host_port = 51366
volume    = anonymous disposable Docker volume only
```

The dump was restored with ownership and privileges excluded and restore error stopping enabled. Before migration, the clone had:

- exact revisions `20260830_0023` and `20260901_0021`;
- 39 public tables;
- exact per-table row-count parity with the captured real database counts;
- Company Profile count and ID parity;
- no `singleton_key` column.

A raw JSON representation differed only because the two PostgreSQL environments rendered timestamp text differently. After normalizing timestamps to UTC, the entire Company Profile row matched exactly, with SHA-256:

```text
066c8f244e43a272a8f8828a832e7ab3880681b976ae078c4cad0c50cfc24a70
```

## 7. Clone migration rehearsal

Only the disposable clone was upgraded:

```text
20260830_0023 -> 20260831_0024
20260831_0024 + 20260901_0021 -> 20260902_0025
20260902_0025 -> 20260902_0026
```

Post-upgrade results:

- one Alembic revision: `20260902_0026`;
- 41 public tables;
- new tables: `stage_transactions`, `load_verification_transactions`;
- no unexpected core-table row-count mismatches;
- Company Profile count remained 1 and ID remained 1;
- `singleton_key` was populated with value 1.

Real PostgreSQL constraint enforcement was verified:

| Constraint | Result |
|---|---|
| `uq_company_profiles_singleton_key` | duplicate rejected, SQLSTATE `23505` |
| `ck_company_profiles_singleton_key_is_one` | invalid value rejected, SQLSTATE `23514` |
| `singleton_key NOT NULL` | null rejected, SQLSTATE `23502` |

The rehearsal also covered the downgrade from 0026 to 0025 and re-upgrade from 0025 to 0026 as part of the validated migration scenarios from PHASE 12.1C; this phase independently proved that the retained real-data dump restores and advances through the accepted graph.

## 8. API and transaction smoke on clone

With the application pointed only at the clone:

```text
GET empty Company Profile       = 404
administrator PUT create        = 200
administrator PUT update        = 200
create/update preserve same ID  = true
audit actions                   = CREATE, UPDATE
Company Profile row count       = 1
forced audit failure response   = 500
rows after forced failure       = 0
audits after forced failure     = 0
```

The forced audit failure proved transaction atomicity: neither the Company Profile row nor its audit event survived.

## 9. Regression tests

Executed from the existing backend virtual environment with `DEBUG=false`:

```text
targeted Company Profile tests = 18 passed
complete Python suite          = 170 passed, exit code 0
```

The full suite used an explicit disposable pytest base directory because the Windows default pytest temporary root was inaccessible. The explicit directory was removed after the successful run.

## 10. Cleanup evidence

- Disposable PostgreSQL container: removed.
- Container presence after removal: false.
- Host port 51366 listener after removal: false.
- Docker-created anonymous volume: precisely identified and removed.
- Anonymous volume presence after removal: false.
- Temporary pytest directory: removed; path presence false.
- Temporary API smoke script: removed through the approved patch mechanism.
- Retained backup: intentionally not deleted.

No container, temporary database, disposable volume, or test directory from this phase remains.

## 11. Final real database unchanged proof

After clone migration, API smoke, tests, and cleanup, a final read-only query against the real database returned:

```text
identity             = dlx_yuki_wms / dlx_user / ::1/128 / 5432
revisions            = 20260830_0023, 20260901_0021
company_profile_rows = 1
company_profile_ids  = 1
singleton_key_column = absent
```

This matches the entry precheck. The real WMS database was not upgraded or modified.

## 12. PHASE 12.1D-B controlled real-upgrade runbook (not executed)

PHASE 12.1D-B remains unauthorized until explicitly started. When authorized, execute it as an isolated maintenance operation:

1. Establish and announce a maintenance window; stop all application and operator writes.
2. Record `git status --short`, staged/unstaged name-status, source HEAD, `alembic heads`, and SHA-256 for migrations 0025 and 0026. Require the exact accepted graph and hashes recorded above.
3. Create a fresh real-database custom-format backup outside the repository. Verify non-zero size, SHA-256, and successful `pg_restore --list` before proceeding.
4. Using read-only queries, verify database identity and endpoint, revisions exactly `20260830_0023` plus `20260901_0021`, and Company Profile row count no greater than one. Stop on any mismatch.
5. Confirm the write freeze remains effective and no unexpected sessions are performing application writes.
6. Set the migration connection explicitly to the verified real database and execute only:

   ```text
   alembic upgrade 20260902_0026
   ```

7. Do not use `alembic stamp`; do not edit migrations 0025/0026; do not mix Settings, Java, frontend, or unrelated development into the window.
8. Verify one revision `20260902_0026`, expected schema objects, singleton constraints, Company Profile identity/count, and absence of unexpected row-count changes.
9. Run Company Profile GET and administrator PUT smoke, verify CREATE/UPDATE audit behavior and atomicity, then run baseline application health checks before reopening writes.
10. If any migration or verification step fails, keep writes frozen, preserve logs and evidence, do not delete or alter Company Profile data to bypass the failure, and restore using the verified backup under the documented recovery procedure.

## Decision

All 12.1D-A gates passed: source integrity, real read-only state, recoverable backup, clone restore parity, clone migration, PostgreSQL constraints, API behavior, atomicity, regressions, cleanup, and final unchanged-real-database verification.

```text
PHASE_12_1D_A = READY_FOR_PHASE_12_1D_B
```

This is readiness evidence only. It is not authorization to run PHASE 12.1D-B.
