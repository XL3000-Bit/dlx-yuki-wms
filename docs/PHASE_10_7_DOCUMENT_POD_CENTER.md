# PHASE 10.7 Document & POD Center Foundation

Inspection: `docs/CURRENT_DOCUMENT_ARCHITECTURE_ASSESSMENT.md`.
This phase does not start PHASE 10.8.

## Domain

`OperationalDocument` links one file to at least one of: Load, Outbound, BOL, Work Order, Exception, Container. Warehouse is required and inherited from the parent. Cross-warehouse binds are rejected.

## Document types

BOL, POD, DELIVERY_RECEIPT, WAREHOUSE, EXCEPTION_ATTACHMENT, GENERAL.

Existing `BOL` table is unchanged.

## Statuses

Common: DRAFT, AVAILABLE, SUPERSEDED, ARCHIVED.
POD uploaded files use RECEIVED (treated as available for download). Load UI shows Pending POD vs POD Received from whether an AVAILABLE/RECEIVED POD exists. Load transportation status is not changed.

## Storage

`LocalFileStorage` (`save` / `open` / `delete` / `exists` / `metadata`) under `DOCUMENT_STORAGE_DIR` (default `./storage/documents`). Keys are date + uuid + sanitized name. Business services do not concatenate raw paths. Tests force a temp directory.

## Upload safety

Allow: pdf, xlsx, xls, csv, jpg, jpeg, png.
Deny: exe, bat, cmd, ps1, js, html, htm, msi, sh, com.
Max size: `DOCUMENT_MAX_BYTES` (15MB).
Filenames are basenamed and sanitized; `..` cannot escape the storage root.
Failed DB commit deletes the written file.

## Versioning

BOL / POD / DELIVERY_RECEIPT / WAREHOUSE: next version, previous AVAILABLE/RECEIVED/PENDING becomes SUPERSEDED. Old file is kept.
GENERAL / EXCEPTION_ATTACHMENT: multiple AVAILABLE rows allowed.

## BOL integration

After `POST /outbounds/{id}/bol`, the generated PDF is registered as type BOL pointing at the stored copy. Live `/bols/{id}/pdf` still streams from the generator. Existing BOL is not deleted.

## POD workflow

Upload type POD on a Load (or Outbound). Document status RECEIVED. Load is not auto-completed.

## Integrations

- Load / Work Order / Trouble Shoot drawers use `DocumentsPanel` (metadata only).
- Exception upload writes `DOCUMENT_ATTACHED` on the exception timeline (id/type/name only, no base64).
- Documents page at `/documents` with search, type, status, warehouse, selected drawer.

## RBAC / scope

PHASE 10.5 warehouse scope on list/detail/download. Viewer can list/download, cannot upload/archive. Out-of-scope ids return 404. Outbound-ish types require outbound write roles; warehouse types require warehouse write roles.

## API

- GET /api/v1/documents
- GET /api/v1/documents/{id}
- GET /api/v1/documents/{id}/events
- GET /api/v1/documents/{id}/download
- POST /api/v1/documents/upload
- POST /api/v1/documents/{id}/archive

## Global Search

DOCUMENT group: document_no, file_name, original_file_name, related BOL number. Route `/documents?selected=`.

## Migration

`20260830_0019_operational_documents` revises `20260830_0018`.

## Known limitations

- No OCR, EDI, email, e-sign, S3, portals, or automatic POD chase.
- Outbound workbench does not embed the panel; use Documents page + `outbound_id` filter or Load drawer.
- Generated XLSX is not separately registered (PDF is the registered BOL file).
- Download events are not audited.
