# CURRENT_DOCUMENT_ARCHITECTURE_ASSESSMENT

## Scope reviewed

The Phase 10.7 review covered the current BOL/Picking download endpoints, import upload handling, filesystem configuration, entity relationships, Phase 10.5 RBAC and scope helpers, global search, API routing, migrations, and the Load/Outbound/BOL/Work Order/Exception frontend surfaces.

## Current state

- BOL PDF and XLSX files are generated in memory on every request. A `BOL` business record exists, but no durable document metadata record is created and no physical BOL copy is stored.
- Picking XLSX files are also generated in memory and returned directly.
- Import uploads use a feature-specific upload directory and JSON sidecar files. That mechanism is an import staging facility, not an operational document repository, and it has no reusable document lifecycle, versioning, business links, or document events.
- `OutboundOrder.pod_reference` and `bol_reference` are text references only. There is no upload/download lifecycle or authoritative POD document state.
- Load, Outbound, BOL, Work Order, Operational Exception, and Container Tracking already expose stable foreign-key relationships and warehouse ownership suitable for document linking.
- Phase 10.5 supplies warehouse/customer scope clauses and write-role dependencies. Viewer is read-only; outbound and warehouse writers have distinct mutation roles.
- Global search is a bounded, scoped multi-entity search and can be extended with a `DOCUMENT` result group.
- There is no shared storage interface, path containment policy, extension whitelist, maximum-size enforcement, document status/version model, append-only document event stream, or cleanup strategy spanning database and filesystem failures.

## Foundation decision

Phase 10.7 will add one `OperationalDocument` metadata model and one append-only `DocumentEvent` model. Binary content remains outside the database behind a local-filesystem storage abstraction. A document must link to at least one supported business entity, and every link must resolve to the same warehouse context.

Generated BOL output will retain its existing dynamic endpoint and business model. The document center will register BOL metadata that points to a virtual generated artifact, avoiding physical duplication. Uploaded files will use opaque generated storage keys beneath a configured root; client filenames are metadata only and never become filesystem paths.

Document visibility and download will derive from the document warehouse/customer scope. Upload/archive will require the appropriate Phase 10.5 write role for the linked business context. Viewer users may list, inspect, view events, and download visible documents, but may not mutate them.

Version replacement applies to single-current business document types such as BOL, POD, delivery receipts, and warehouse documents. `GENERAL` and `EXCEPTION_ATTACHMENT` remain coexistence types. Superseding changes metadata status only and does not delete historical bytes.

POD receipt is represented by an available POD document linked to an outbound or load. It does not transition transport, load, outbound, exception, or work-order workflow status.

## Migration and compatibility constraints

- Additive migration only: `operational_documents` and `document_events`, enums/checks, foreign keys, and scoped lookup indexes.
- Existing BOL, outbound, import, load, work-order, and exception records and endpoints remain valid.
- No OCR, EDI, email ingestion, e-signature, cloud object storage, or workflow automation is included.
