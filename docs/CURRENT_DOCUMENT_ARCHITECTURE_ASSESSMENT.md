# CURRENT_DOCUMENT_ARCHITECTURE_ASSESSMENT

Source: `phase-10.3-work-order-audit` after PHASE 10.6.
Date: 2026-08-30.

## Existing BOL storage

`bols` / `bol_items` are business records (ship from/to, quantities, status int). There is **no** file path, blob, or version column on BOL.

## Existing generated files

- `GET /bols/{id}/pdf` builds a minimal PDF **in memory** via `bol_pdf()` and returns bytes.
- `GET /bols/{id}/xlsx` and picking XLSX also stream from `BytesIO`.
- Regenerating BOL (`POST /outbounds/{id}/bol`) returns the existing row if one already exists. Physical files are never written to disk.

## Existing upload support

Import endpoints accept Excel for inbound/inventory/FBA/outbound. That pipeline stores import **jobs/rows**, not operational attachments. `python-multipart` is already a dependency.

## Existing download support

Authenticated streaming responses only. No generic attachment download endpoint and no storage key.

## Existing attachment fields

Outbound has string `bol_reference` / `pod_reference`. Load detail UI previously said "No persisted document or history records." Exception events are text/metadata only.

## Existing storage location strategy

None. Config had no document directory. Imports use `backend/data/imports/`.

## Missing document lifecycle

No OperationalDocument, no version/supersede, no POD received flag separate from Load status, no scoped download, no Document Center page.

## Decision

Keep the BOL business model. Add OperationalDocument as metadata + lifecycle over a local filesystem abstraction. Register generated BOL PDF as a document without replacing `/bols/{id}/pdf`.
