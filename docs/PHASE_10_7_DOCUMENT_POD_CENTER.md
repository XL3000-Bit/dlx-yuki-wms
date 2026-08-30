# PHASE 10.7 — Document & POD Center Foundation

## Scope

PHASE 10.7 adds a warehouse-scoped operational document registry and local file storage foundation. It covers BOL metadata, POD and delivery receipts, warehouse documents, exception attachments, general documents, version history, controlled downloads, and integrations with loads, outbound orders, work orders, exceptions, and container tracking.

OCR, EDI, email ingestion, electronic signatures, and cloud object storage are intentionally outside this phase.

## Data model and migration

Alembic revision `20260830_0019` follows scoped RBAC revision `20260830_0018` and creates:

- `operational_documents`, including document number, type, lifecycle status, version, original filename, content metadata, SHA-256 checksum, storage key, generated-file marker, warehouse/customer scope, actor fields, and nullable business links.
- `document_events`, an append-only application event timeline for create, upload, availability, supersede, and archive actions.
- Scope, lifecycle, filename, relationship, actor, and timeline indexes.
- Database constraints requiring a positive version and at least one business relationship.

Supported types are `BOL`, `POD`, `DELIVERY_RECEIPT`, `WAREHOUSE`, `EXCEPTION_ATTACHMENT`, and `GENERAL`. Lifecycle statuses are `DRAFT`, `AVAILABLE`, `SUPERSEDED`, and `ARCHIVED`.

## Storage and upload safety

`LocalDocumentStorage` is the first implementation of the storage boundary and exposes save, open, delete, exists, and metadata operations. Storage keys are server-generated and resolved below the configured storage root. Absolute keys, parent traversal, and Windows separator injection are rejected.

Uploads are streamed in bounded chunks, limited by `DOCUMENT_MAX_UPLOAD_BYTES`, hashed with SHA-256, and restricted to PDF, XLSX, XLS, CSV, JPG, JPEG, and PNG extensions. A failed stream or database transaction removes the partially stored object. Tests override the storage root with an isolated temporary directory.

## Versioning

Uploading the same document type against the same business relationship increments the version and supersedes earlier available versions. `GENERAL` and `EXCEPTION_ATTACHMENT` documents coexist without superseding one another. Supersede operations append events to both the previous and new records.

Generated BOL output remains owned by the established BOL subsystem. The document registry stores metadata and a logical relationship only; download renders from the source BOL and does not duplicate the generated binary in local storage.

## API

The `/api/v1/documents` resource provides scoped list/search/filter, detail, multipart upload, controlled download, archive, and event-history endpoints. Relationship resolution validates that all linked records share one warehouse and compatible customer scope before the document is persisted.

POD and delivery-receipt uploads are evidence-only operations. They do not change load, outbound, dispatch, or work-order state and do not auto-complete transportation workflows.

## Authorization and visibility

All queries and downloads pass through Phase 10.5 warehouse/customer visibility rules. Viewers can list, inspect, and download visible documents. Upload, supersede, and archive actions require the appropriate warehouse or outbound management permission. Cross-warehouse relationships and inaccessible entity identifiers are rejected.

## User interface and integrations

The Document & POD Center provides search, type/status filters, pagination, version/status indicators, a POD badge, upload, download, archive, and an event-history drawer. Global search returns `DOCUMENT` results and links directly to the selected document drawer.

Reusable document panels are embedded in load detail, outbound dispatch detail, exception detail, and work-order detail. Each panel applies its entity relationship automatically when uploading.

## Verification

The focused PHASE 10.7 suite covers POD behavior, download and event history, superseding and coexistence, upload size and path safety, compensating cleanup, viewer permissions, cross-warehouse rejection, work-order attachment/archive, and global search. The complete backend regression suite and production frontend build are the release gates for this phase.

## Known limitations

- Local storage is intended as a replaceable foundation; multi-node deployments require a shared storage implementation.
- File acceptance is based on an explicit extension allowlist and size boundary; antivirus scanning and deep content inspection are not included.
- Document events are append-only through the public application API; database-level immutability triggers are not included.
- Generated BOL content is rendered on download from the current BOL snapshot rather than retained as a separately stored binary.
