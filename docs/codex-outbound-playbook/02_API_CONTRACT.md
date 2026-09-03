# Outbound API Contract

API prefix: `/api/v1`

## Workbench queries

`GET /api/v1/outbounds/workbench` supports only these approved filter, paging, and sorting parameters:

- `q`
- `status`
- `ob_type`
- `warehouse_id`
- `carrier_id`
- `page`
- `per_page`
- `sort_by`
- `sort_order`

Do not invent dedicated backend filter fields. Additional search inputs continue to feed `q` where applicable unless a later approved contract change is proven necessary.

## Batch operations

The batch endpoint is:

`POST /api/v1/outbounds/workbench/batch`

Its actual response model is:

```json
{
  "results": [
    {
      "id": 1,
      "status": "success|failed",
      "reason": "..."
    }
  ],
  "successful": 1,
  "failed": 1
}
```

Warning: `outbound_id`, `succeeded`, and `total` are incorrect assumptions for fields in this batch response and must not be used as response fields.

Supported batch action names are:

- `picking`
- `bol`
- `confirm`
- `dispatch`
- `complete`
- `cancel`

Where a Slice requires batching, a multi-select operation must issue exactly one batch POST rather than loop over single-record endpoints.

## Dispatch readiness

Before dispatch, use:

`GET /api/v1/outbounds/{id}/dispatch-readiness`

The implementation and reconciliation must determine how readiness is represented. When dispatch is blocked, the UI must expose the actual `blocking_reasons`; it must not replace them with a generic failure message.

## Approved existing endpoint baseline

```text
GET    /api/v1/outbounds/workbench
GET    /api/v1/outbounds/{id}/workbench-detail
POST   /api/v1/outbounds
PATCH  /api/v1/outbounds/{id}/schedule
POST   /api/v1/outbounds/{id}/allocate
POST   /api/v1/outbounds/{id}/allocations/{allocation_id}/release
POST   /api/v1/outbounds/{id}/confirm
POST   /api/v1/outbounds/{id}/dispatch
POST   /api/v1/outbounds/{id}/complete
POST   /api/v1/outbounds/{id}/cancel
POST   /api/v1/outbounds/{id}/exception
POST   /api/v1/outbounds/{id}/resolve-exception
GET    /api/v1/outbounds/files/export.xlsx
POST   /api/v1/outbounds/workbench/export-selected
GET    /api/v1/outbounds
GET    /api/v1/outbounds/{id}
PUT    /api/v1/outbounds/{id}
GET    /api/v1/outbounds/{id}/allocations
GET    /api/v1/outbounds/{id}/dispatch-readiness
POST   /api/v1/outbounds/workbench/batch
GET    /api/v1/master-data/customers
GET    /api/v1/master-data/warehouses
GET    /api/v1/master-data/carriers
POST   /api/v1/loads
POST   /api/v1/outbounds/{id}/picking-lists
POST   /api/v1/outbounds/{id}/bol
GET    /api/v1/documents
POST   /api/v1/documents
GET    /api/v1/documents/{id}/download
```

Outbound import endpoints exist but are not the primary target of this playbook.
