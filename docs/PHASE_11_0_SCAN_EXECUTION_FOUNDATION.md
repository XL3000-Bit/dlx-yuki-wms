# PHASE 11.0 — Scan Execution Foundation

## Status and boundary

PHASE 11.0 establishes a keyboard-wedge scan capture and audit foundation on top of the frozen PHASE 10 release candidate. A scan resolves an existing operational identifier, validates access and session context, and records an immutable event. It does not change inventory quantities or advance picking, loading, exception, or outbound statuses.

The detailed pre-implementation model and identifier assessment is recorded in `CURRENT_SCAN_EXECUTION_ASSESSMENT.md`.

## Data model

### ScanSession

A scan session is owned by one user and one warehouse. It records:

- operation type and lifecycle status (`OPEN`, `COMPLETED`, or `CANCELED`);
- optional outbound, picking, and load context;
- creation, last-scan, completion, and cancellation timestamps.

Only active sessions accept ordinary scan capture. Completion and cancellation are explicit terminal actions.

### ScanEvent

Each input attempt creates one append-only event containing:

- raw and normalized scanner values;
- result (`ACCEPTED`, `REJECTED`, `DUPLICATE`, `NOT_FOUND`, `WRONG_WAREHOUSE`, `WRONG_OUTBOUND`, `WRONG_LOCATION`, or `INVALID_STATE`);
- resolved scan type and entity identity when available;
- a structured message and timezone-aware scan timestamp.

There are no update or delete event APIs. Application-level ORM guards and a PostgreSQL trigger reject event updates and deletes. The event history is therefore an operational audit trail, not a mutable work queue.

## Supported identifiers

The resolver performs exact, case-insensitive identifier matching. It does not perform fuzzy matching or infer missing master data.

| Entity | Identifier | Scope/context rule |
| --- | --- | --- |
| Outbound order | `ob_no` | Existing warehouse/customer access scope; must match bound outbound context. |
| Picking list | `picking_no` | Scoped through its outbound order; must match bound picking/outbound context. |
| FBA shipment | `fba_no` | Existing FBA access scope; must match bound outbound where applicable. |
| Warehouse location | `location_code` | Unique inside the session warehouse; constrained to the bound picking list where applicable. |
| Inventory lot | `lot_no` | Must be visible in the session warehouse and allocated to the bound outbound where applicable. |
| Container | `container_number` | Resolves matching inventory lots in the session warehouse; must belong to the bound outbound where applicable. |

`load_no` can bind and validate a session context, but load scan execution is not introduced in this phase. Pallet/LPN and SKU scanning remain unsupported because the frozen schema does not provide stable identifiers for those entities.

## Normalization and duplicate behavior

- Leading/trailing scanner whitespace is trimmed and CR/LF transport characters are removed.
- Empty normalized input is recorded as `REJECTED` with an explicit validation message.
- The raw input and normalized value are both retained for audit.
- Identifier matching and accepted-value duplicate detection are case-insensitive.
- A value accepted earlier in the same session creates a new `DUPLICATE` event.
- Duplicate scans never increment inventory or completion quantities.

## API

The API is mounted under `/api/v1/scan-sessions` and remains additive to existing routes.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/` | Create a warehouse-bound open session with optional execution context. |
| `GET` | `/{session_id}` | Read session state, counters, and recent events. |
| `GET` | `/{session_id}/events` | Read paginated append-only event history. |
| `POST` | `/{session_id}/scan` | Submit exactly `{ "value": "..." }` for resolution and audit. |
| `POST` | `/{session_id}/complete` | Complete an open session. |
| `POST` | `/{session_id}/cancel` | Cancel an open session. |

The scan route uses an explicit transaction: validation, event insertion, session timestamp update, and commit succeed together or roll back together.

## Permissions and data isolation

- Session reads use the caller's existing PHASE 10.5 warehouse/customer scopes.
- Session creation, scanning, completion, and cancellation require the existing outbound-management permission.
- A non-admin user can access only their own sessions.
- Context identifiers are validated when the session is created and again through scoped resolver queries.
- An unauthorized cross-warehouse entity remains `NOT_FOUND` so the API does not disclose inaccessible identifiers.
- This phase adds no roles, permission names, or authentication rules.

## Scan Workbench

The `/scan-execution` page provides a high-density desktop workflow for keyboard-wedge scanners:

- operation and warehouse selection with optional outbound/picking/load context;
- a large autofocus input that submits on Enter;
- Escape to clear and restore focus;
- immediate inline result state and optional local Web Audio feedback;
- accepted, duplicate, rejected, and total counters;
- the 20 most recent immutable scan events;
- explicit complete, cancel, refresh, and new-session controls;
- session identity persisted in URL query state.

The page consumes backend results only. It does not mutate inventory or independently reproduce execution business rules.

## Migration and PostgreSQL behavior

Migration `20260830_0022_scan_execution_foundation` adds only the scan session/event tables, their constraints and indexes, and the PostgreSQL append-only trigger. It does not alter PHASE 10 business tables or data. Timestamps use timezone-aware database columns.

## Acceptance criteria

- One Alembic head, a clean `alembic check`, and a successful fresh PostgreSQL upgrade to head.
- PostgreSQL runtime verification of session creation, accepted/duplicate/rejected events, terminal session behavior, event pagination, indexes, and append-only enforcement.
- Full backend test suite and Python compilation pass.
- Frontend TypeScript production build passes.
- Browser smoke verifies authentication, session creation, autofocus/Enter/Escape behavior, accepted/duplicate/not-found presentation, counters/history, URL restoration, and terminal controls.
- Regression verification confirms that scans do not change allocation quantities, inventory balances, or existing workflow statuses.

## Acceptance result

- Alembic has one head at `20260830_0022`; `alembic check` reports no drift.
- A fresh PostgreSQL 17 schema upgraded from base to head successfully.
- The migration round trip `0022 -> 0021 -> 0022` completed successfully.
- PostgreSQL runtime smoke verified `ACCEPTED`, `DUPLICATE`, `NOT_FOUND`, and terminal-session `INVALID_STATE` events, descending event history, timezone-aware `scanned_at`, required indexes, and database-enforced append-only events.
- Python `compileall` passed.
- The directed scan-execution backend suite passed: 8 tests.
- The full backend suite passed: 127 tests.
- The frontend production build passed. The frontend package currently has no lint or unit-test script.
- Browser smoke verified session creation, autofocus keyboard-wedge input, first-scan acceptance, duplicate detection, unknown-code rejection, counter updates, newest-first history, Escape-to-clear, and completed-session input/action locking.
- `git diff --check` passed.

## Explicit non-goals and deferred work

- Scan-driven quantity execution or status transitions.
- Picking confirmation, loading, dispatch, POD, or exception resolution workflows.
- Pallet/LPN or SKU master-data creation.
- Camera/mobile scanning, offline queues, batch quantities, or device management.
- Any PHASE 11.1 behavior.

## Known limitations

- The current schema has no stable pallet/LPN or SKU barcode, so those scans are not guessed from quantity or description fields.
- A container number can represent multiple inventory lots; the event resolves the container reference without pretending it is a unique lot identifier.
- Operational business time remains the configured global timezone (`America/Los_Angeles` by default); per-warehouse timezones are not supported.
- Audio feedback depends on browser Web Audio availability and user/browser media policy; visual feedback remains authoritative.
- This phase intentionally provides session-scoped history rather than a cross-session scan-event search or reporting module.
