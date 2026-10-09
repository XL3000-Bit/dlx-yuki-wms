# PHASE 10.0 — Global Multi-Reference Search MVP

## Architecture

The authenticated `GET /api/v1/search` endpoint performs read-only, bounded searches across existing operational models. Each model is queried once with its real reference columns, candidates are deduplicated by model and primary key, ranked in application code, capped globally, and returned in typed groups. No operational business rules are changed.

## Searchable entities and fields

| Entity | Existing fields searched |
| --- | --- |
| Container Tracking | `container_number`, `mbl_number`, `hbl_number`, `filing_number`, `customer_reference` |
| Outbound | `ob_no`, `reference_no`, `appointment_reference`, `picking_reference`, `bol_reference`, `pod_reference` |
| FBA | `fba_no`, `reference_no`, `shipment_id`, `st_number`, `po_number`, `source_reference` |
| Picking | `picking_no` |
| BOL | `bol_no` |

No fields were added to satisfy the candidate list. Inbound and inventory container values are intentionally represented by the canonical Container Tracking result in this MVP rather than creating duplicate navigation choices.

## Ranking

Matching is case-insensitive. Exact matches rank first, prefix matches second, and contains matches third. A record matching more than one of its fields is returned only once. Results are capped by the requested global `limit` (default 20, range 1–50). Each entity query also has an internal candidate cap of 20–150 rows, derived from the global limit.

## API

`GET /api/v1/search?q=<text>&limit=<optional>`

Queries are trimmed and must contain at least two characters. Invalid short/blank queries return HTTP 422. The response contains normalized `query`, `total`, and non-empty `groups`; each item provides type, ID, primary/secondary reference, status, available warehouse/customer labels, route, and match rank.

## Frontend UI

`GlobalSearch` is mounted in the existing `AppLayout` header without restructuring the layout. It provides 300 ms debounce, Enter activation, loading/empty/error states, Up/Down selection, Escape dismissal, click-outside dismissal, and grouped operational results. Styling retains the compact DLX orange office theme.

## Navigation behavior

- Container: `/container-tracking?selected=<id>` opens the existing drawer.
- Outbound: `/outbound/dispatch?selected_ob=<id>` reuses the workbench URL state and does not overwrite unrelated filter, pagination, or sorting state while already on that route.
- FBA: `/fba?selected=<id>` reuses the FBA workbench selection state.
- Picking: `/outbound/picking`, the existing list page (no fake detail route).
- BOL: `/outbound/bol`, the existing list page (no fake detail route).

## Database and index changes

No migration was added. Primary reference columns (`container_number`, `ob_no`, `fba_no`, `picking_no`, and `bol_no`) and most secondary operational references already have indexes. Leading-wildcard contains matches cannot reliably use ordinary b-tree indexes, so the MVP bounds every entity query rather than introducing database-specific trigram infrastructure. This is lower risk at the current operational-core beta scale.

## Security behavior

The endpoint uses the same `CurrentUser` bearer-token dependency as the existing read APIs. The current codebase does not implement per-user warehouse/customer row scopes on those list/detail APIs, so global search intentionally neither invents a new RBAC model nor broadens access beyond the current authenticated read scope.

## Tests

Backend coverage includes exact, prefix, contains, blank/whitespace validation, global limit, duplicate prevention, unknown references, authentication, and cross-model grouping. The frontend has no existing test runner; TypeScript and production bundling are verified with `npm run build`.

## Known limitations

- Contains matching uses bounded SQL `LIKE` queries; matches beyond an entity candidate cap can be omitted for extremely broad queries.
- Picking and BOL currently have list pages only, so search navigates to those real pages without opening a nonexistent detail view.
- Visibility follows the system's present authenticated read scope; finer warehouse/customer scoping should be inherited when the underlying APIs gain it.
