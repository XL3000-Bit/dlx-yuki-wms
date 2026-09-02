# PHASE 12.1C — Disposable PostgreSQL Migration Rehearsal

## Final status

```text
PHASE_12_1C = BLOCKED
BLOCK_REASON = NO_DISPOSABLE_POSTGRESQL
```

The migration rehearsal was not started. No Alembic DDL, upgrade, downgrade,
or stamp command was run against any database.

## A. Modified and created files

- Created this report only: `docs/PHASE_12_1C_POSTGRES_MIGRATION_REHEARSAL.md`.
- No migration, application, test, Java, frontend, Nginx, PDA, or ThreePL file
  was changed by this task.

## B. Pre-operation workspace state

- Branch: `feature/java-api-parity`
- HEAD: `cefe1a23b9779b71ce9c7097b0fdf020a14bca6d`
- The worktree already contained numerous tracked and untracked changes across
  `backend-java`, Python backend, frontend, docs, and Nginx.
- `git diff --cached --name-status` was empty.
- All pre-existing changes were left in place.

## C. Isolated PostgreSQL method considered

1. Docker CLI was present, but the Docker Desktop Linux engine was not
   available (the engine named pipe did not exist). No container was started.
2. Local PostgreSQL 17 was running on localhost port 5432, and the PostgreSQL
   17 client tools were available.
3. The existing application credential could authenticate only to the local
   maintenance database for a read-only capability check. It is neither a
   superuser nor a role with `CREATEDB`.
4. The local `postgres` administrative role had no available non-interactive
   credential. No password was requested, printed, or persisted.

Consequently, this task could not create a newly isolated database whose name
contained both `dlx_yuki_wms` and `migration_rehearsal`. Reusing the application
database or a schema inside an existing database was rejected as unsafe and
non-compliant.

## D. Temporary database safety-gate evidence

The maintenance connection reported:

```text
current_database = postgres
current_user = dlx_user
server_address = ::1
server_port = 5432
role_createdb = false
role_superuser = false
```

Because no temporary database could be created, there was no migration target
on which to collect table count or `alembic_version`. The DDL safety gate was
therefore not satisfied and execution stopped before any migration.

## E. PostgreSQL version

```text
PostgreSQL 17.11 on x86_64-windows, 64-bit
```

## F–N. Migration scenarios

The following scenarios were **not run** because a safe disposable PostgreSQL
database was unavailable:

- F. Blank database full upgrade to `20260902_0026`.
- G. Real dual-revision reconstruction and merge upgrade.
- H. Zero-row Company Profile migration.
- I. One historical Company Profile migration.
- J. Multiple-row expected migration failure.
- K. Transactional schema rollback after the expected failure.
- L. PostgreSQL UNIQUE, CHECK, and NOT NULL enforcement.
- M. Downgrade from `0026` to `0025`.
- N. Re-upgrade from `0025` to `0026`.

Static inspection or SQLite was deliberately not substituted for these checks.

## O. Company Profile data preservation

Not runtime-verified in this phase because no disposable migration target was
available.

## P. API smoke

GET-empty-state and administrator PUT-create smoke were not run against
PostgreSQL. No application process was pointed at a different database.

## Q. Audit atomicity

Not runtime-verified against PostgreSQL in this phase.

## R–S. Test results

Targeted and complete Python tests were not rerun because the mandatory real
PostgreSQL rehearsal could not begin. The prior PHASE 12.1B result remains
separate and is not used to promote this phase to PASS.

## T. Alembic results

No `alembic current`, `upgrade`, `downgrade`, or `stamp` command was executed
against the application database or any other database. The migration source
was inspected as specified, but source inspection is not runtime verification.

## U. Actual WMS database

The configured application database name was identified without printing the
connection string. This task did not connect to that database and did not run
any DDL or Alembic operation against it. Its revision and business data were
not modified by this task.

## V. Cleanup

- Temporary databases created: 0
- Containers created: 0
- Volumes created: 0
- Background migration/test processes created: 0

There were therefore no disposable resources to remove.

## W. Git diff check

`git diff --check` completed without whitespace errors. Git emitted only the
existing Windows line-ending conversion warnings.

## X. Worktree preservation

No pre-existing modification or untracked file was removed, restored, stashed,
staged, committed, or pushed. No reset, checkout, clean, or restore operation
was used.

## Y. Need to correct migration 0026

No correction is justified from this phase. No real PostgreSQL failure evidence
was produced, so `20260902_0026_company_profile_singleton.py` remains unchanged.

## Z. Readiness for actual database upgrade

**Not allowed.** A controlled actual-database upgrade must not begin until this
rehearsal is rerun on a genuinely disposable PostgreSQL database and satisfies
all PASS conditions.

## Unblock requirement

Provide exactly one of the following without changing the real WMS database:

- a running disposable Docker PostgreSQL instance/container, or
- permission and credentials capable of creating and dropping a newly named
  local database dedicated to this rehearsal.

Do not grant broader production access merely to unblock this test.

## RETRY — Disposable PostgreSQL Rehearsal

### Retry result

```text
PHASE_12_1C                = PASS
BLOCK_REASON               = CLEARED
SOURCE_MIGRATION_GRAPH     = PASS
POSTGRES_RUNTIME_REHEARSAL = PASS
REAL_WMS_DATABASE          = UNCHANGED
ACTUAL_DATABASE_UPGRADE    = NOT_RUN
SCOPE_CONTROL              = PASS
```

The original `BLOCKED` record above is retained as historical evidence. This
retry began only after `docker version`, `docker info`, and `docker ps`
confirmed that both the Docker client and Docker Desktop server were
available.

### Retry safety baseline

- Repository HEAD: `cefe1a23b9779b71ce9c7097b0fdf020a14bca6d`.
- The pre-existing dirty worktree was recorded before the retry and preserved.
- The staged diff was empty. Nothing was staged, committed, pushed, stashed,
  reset, restored, or cleaned.
- Every application and Alembic process in this rehearsal received an explicit
  disposable `DATABASE_URL`. The current application `DATABASE_URL` was not
  read or used.
- No connection to the real WMS database was made during the retry. Therefore
  no real revision query or upgrade was attempted.
- Java, frontend, Nginx, and unrelated business modules were not modified.

### Disposable PostgreSQL isolation

The retry used a new `postgres:17-alpine` container with the following
non-secret identifiers:

```text
container = dlx-yuki-wms-migration-rehearsal-05bed1dc74
database  = dlx_yuki_wms_migration_rehearsal_05bed1dc74
host port = 51523
test dir  = C:\Users\XL\AppData\Local\Temp\dlx-yuki-wms-rehearsal-05bed1dc74
```

The database password and JWT secret were independently randomized and were
not written to this report. No existing volume or bind mount was attached.
PostgreSQL's image-created anonymous volume was tracked by ID for cleanup.

### PostgreSQL evidence and migration 0026 correction

The first real PostgreSQL constraint-name check exposed a migration defect:
`op.create_check_constraint` was given the already-prefixed name
`ck_company_profiles_singleton_key_is_one`, while the project's SQLAlchemy
naming convention also supplies the `ck_company_profiles_` prefix. PostgreSQL
therefore received a duplicated physical name rather than the contract name.

This was concrete PostgreSQL failure evidence, so the still-uncommitted
`20260902_0026_company_profile_singleton.py` was corrected to pass the logical
name `singleton_key_is_one` to both create and drop operations. No table shape,
data rule, or other migration was changed.

```text
0026 SHA-256 before = 750E733F06B707B77B8283AF01A3E23FF041A2B807963AEAD7D744DAC4550CCB9
0026 SHA-256 after  = 1B9D1C20187F12C958B665A40741074C270E7A8984158F3D856D613063111CE9B
```

After that correction, every migration scenario below was recreated and run
again from the beginning.

### Migration scenario results

```text
Blank database base -> 20260902_0026
  PASS: revision=20260902_0026, tables=41, company_profiles rows=1

Construct real dual revision state
  PASS: revisions=20260830_0023,20260901_0021

Dual revision state -> 20260902_0026
  PASS: revision=20260902_0026

Company Profile zero historical rows
  PASS: rows=0, revision=20260902_0026

Company Profile one historical row
  PASS: rows=1, singleton_key=1, revision=20260902_0026

Company Profile multiple historical rows
  PASS: migration failed safely as required
  rollback evidence: revision=20260902_0025, rows=2,
                     singleton_key column absent, singleton constraints absent

PostgreSQL constraint names
  PASS: ck_company_profiles_singleton_key_is_one
        uq_company_profiles_singleton_key

PostgreSQL constraint enforcement
  PASS: UNIQUE rejected duplicate singleton
  PASS: CHECK rejected singleton_key != 1
  PASS: NOT NULL rejected null singleton_key
  post-failure state: rows=1, singleton_key=1

Downgrade 20260902_0026 -> 20260902_0025
  PASS: revision=20260902_0025, singleton_key column absent

Re-upgrade 20260902_0025 -> 20260902_0026
  PASS: revision=20260902_0026, singleton constraints=2
```

### API and audit-transaction smoke

The FastAPI test client was bound to the disposable database and used a
temporary administrator created only inside it.

```text
GET company profile before creation = 404
administrator PUT create            = 200
persisted company profile rows       = 1
CREATE_COMPANY_PROFILE audit rows    = 1
```

For atomicity, a disposable PostgreSQL trigger deliberately rejected the audit
insert. The PUT returned 500, and the transaction left both the company profile
row count and matching audit row count at zero. This proves the profile create
and `CREATE_COMPANY_PROFILE` audit write roll back together.

### Python tests

```text
Targeted: tests/test_company_profile.py
Result:   18 passed

Full suite:
Result:   170 collected, completed successfully (0 failure, 0 error)
```

The first full-suite invocation encountered 13 setup errors caused by Windows
permissions on pytest's shared user temp directory; it had no assertion
failures. Re-running the same full suite with a task-private `--basetemp`
completed successfully. This was an isolated test-infrastructure issue, not an
application or migration failure.

### Cleanup evidence

Cleanup ran regardless of the test outcome and targeted only identifiers
created by this retry.

```text
container inspection after docker rm -f -v = no matching container
anonymous volume inspection                = no such volume
temporary test directory exists            = False
```

Deleting the container removed its disposable database. The persistent shell
was then closed after clearing its disposable `DATABASE_URL` and JWT secret.
No pre-existing Docker resource was removed.

### Retry conclusion

All required PostgreSQL migration, rollback, constraint, API, audit atomicity,
targeted-test, full-test, and cleanup gates passed. `PHASE_12_1C = PASS` applies
only to this disposable rehearsal. It does not authorize or perform an upgrade
of the real WMS database, and Settings frontend work remains paused.
