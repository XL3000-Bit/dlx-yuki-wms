# PHASE 11.2 — Outbound parity evidence reconciliation

## Decision

The accepted recovery semantics have been ported onto the repaired live-main integration branch and have not been integrated into `main`:

1. source `cc60e3d442bf263bf55e55a695f4e640e0108860`, integration `47c9eb6` — safe outbound deletion and idempotent batch inventory actions;
2. source `29f86278f6efd2202fcaa77a67d32acfafb9a0d0`, integration `8ceefbb` — idempotent Picking/BOL ensure operations and atomic document creation during outbound confirmation;
3. source `78798157baa479155ab643da886add62a86e2af2`, integration `0fc8725` — read-only 3PL dispatch queue workbench.

The integration is based on live-main `bf1ca5f`, followed by the reviewed baseline repairs `ebcecc2` and `fe9a87b`. Migration `20260904_0026` is supplied by the minimal integration prerequisite `d6ceda5`; it is not a transplant of the broader source commit that originally introduced that revision.

The rejected 3PL commit `321554f0042ecb33c7f01dfd0806ff53c351f104` is `QUARANTINED_SCOPE_LEAK`, `NOT ACCEPTED`, and `NOT IN VALID CHAIN`. It was not integrated or used as an evidence source because it contains rejected branding and an out-of-scope layout change.

## Verified outbound behavior

### Safe deletion

Deletion is intentionally narrow. An outbound can be deleted only while it is a pristine `NEW` draft with no allocations, picking list, BOL, load, exception, or other dependent operational record. The API revalidates these rules in the transaction. Batch deletion returns a result for every selected row, so one rejected row does not conceal successful or failed outcomes for the others; audit records remain server-owned.

### Batch inventory actions

Allocation and release are explicit checkbox-and-button batch actions. Operators select rows and invoke the relevant command; validation, authorization, quantity checks, and transaction rollback remain on the server. The implementation does not provide multi-row drag-and-drop between the Remaining Source and Allocation panels. Any legacy `Drag BOL` text is a button label, not evidence of a drag interaction.

Allocation and release accept a persistent `Idempotency-Key`. The stored receipt and database uniqueness constraint make completed retries replayable and serialize concurrent requests for the same operation key. A key cannot be reused for a different request payload. These guarantees were verified on PostgreSQL; they are not inferred from the browser alone.

Migration `20260904_0027` introduces the persistent outbound inventory idempotency receipts.

### Picking and BOL documents

Picking-list and BOL ensure endpoints reuse the active document pair on a repeat request instead of creating duplicates. Cancelled document history is retained; when no active document remains, ensure creates the replacement permitted by the existing rules. Outbound confirmation performs the active Picking/BOL ensure work in the same database transaction as the status transition. If document creation fails, confirmation rolls back. Page and queue reads do not create documents. Migration `20260904_0028` adds database uniqueness for one active picking list and one active BOL per outbound.

Picking XLSX and BOL PDF/XLSX generation were exercised against synthetic disposable data. This verifies availability and non-empty downloads, not pixel-perfect document layout or production printer compatibility.

## Verified 3PL dispatch queue behavior

The 3PL workbench loads a server-derived dispatch queue with authorization and warehouse/customer scope enforcement, priority and blocker indicators, summary counts, search/filter/sort controls, paging, URL-backed state, refresh/back navigation, outbound navigation, and document links. Missing documents are shown explicitly.

Queue retrieval is read-only: repeated `GET` requests and UI refreshes produced no business-table changes in the PostgreSQL verification. `Issue docs` is a separate, explicit mutation and is not part of queue loading; a queue read never performs an automatic document ensure. The `/3pl` and `/fba` routes retain the shared full-height application layout.

## Brand decision

The accepted interface remains **DLX Yuki WMS V3**. EasyFreight names, logos, colors, copied layouts, and rejected-brand artifacts are not part of the implementation. The historical filename is retained only to preserve the existing documentation location.

## Evidence and verification boundary

The recovered external evidence set contained 503 files. None qualified as safe, accepted external evidence. Environment files, derived media, source candidates requiring sanitization, unverified raw media, and quarantined sensitive files remain outside Git and were neither executed nor modified. Recorder source was not run. Media review could illustrate synthetic checkbox/button flows, but provenance, data-safety, rejected-brand, and legacy-label concerns prevent it from proving product behavior.

The accepted claims instead rest on the commit ancestry, code review, automated backend tests, a disposable PostgreSQL 17 database migrated to `20260904_0028`, frontend typecheck/build, and a fresh isolated Chromium parity smoke. The full backend suite passed with PostgreSQL-only tests skipped in the SQLite run and then exercised separately on PostgreSQL.

## Verification matrix

| Gate | Result |
| --- | --- |
| Targeted SQLite backend tests | 41 passed |
| Full backend suite | 186 passed against the isolated PostgreSQL database, including PostgreSQL-only gates |
| PostgreSQL 17.11 | Database-name guard passed; Alembic head `20260904_0028`; targeted 6 outbound, 3 Picking/BOL, and 1 3PL tests passed |
| Frontend unit tests | NOT_CONFIGURED |
| Frontend lint | NOT_CONFIGURED |
| Frontend typecheck | Passed |
| Frontend production build | Passed; non-fatal chunk-size warning |
| Dedicated Chromium smoke | Passed with synthetic disposable records and an outside-repository persistent profile |

No production database, existing browser session, saved browser identity, or recovered recorder credential was used.

## Known limitations

- No accepted external artifact establishes EasyFreight production behavior or exact UI parity.
- Drag-and-drop is unsupported and is not claimed.
- Frontend unit-test and lint scripts are not configured; typecheck, production build, backend suites, PostgreSQL gates, and browser smoke supply the recorded verification.
- Download checks establish successful non-empty XLSX/PDF output, not visual fidelity or printer compatibility.
- Browser verification used synthetic disposable records and did not access a production database or an existing browser session.
- The integration commits and this document remain on `integration/outbound-recovery-repaired-bf1ca5f`, have not been merged into `main` or pushed, and do not establish live `origin/main` integration; those remain separately authorized actions.
- Production deployment, production data validation, load/performance testing, accessibility certification, and cross-browser certification are outside this recovery slice.
