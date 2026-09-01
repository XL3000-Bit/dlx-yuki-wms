# West Coast 4.0 → Yuki WMS Import Console

Read-only migration pack for `美西仓 - 4.0 (1).xlsx`. Do not upload the 297 MB workbook as-is. Convert to the three official profiles, then import in business order.

Status: assessment only. No production write. Source file stays on the operator PC.

## Scale

| Source sheet | Rows | Distinct containers | Yuki target |
|---|---|---|---|
| 提柜 | 886 | 885 | Container Tracking |
| OL | 7,199 | 809 | Inbound / inventory lots |
| DS | ~29,868 | — | FBA / outbound detail |
| 出库 | 731 | — | Outbound header |

## Import order (do not reverse)

0. Master data — customers, warehouses, locations, and the 141 `仓点` values.
1. 提柜 → Container Tracking.
2. OL → `WEST_COAST_4_0_OL` (`ImportModule.INBOUND`).
3. 出库 + DS → `WEST_COAST_4_0_OUTBOUND` + `WEST_COAST_4_0_DS`. Wait until OL lots reconcile.

## Gates before bulk load

- **仓点 semantics.** 141 values may mix warehouse, FBA FC, HOLD, or status. Do not treat them as `warehouse` until classified.
- **Customer codes.** Source names must resolve to Yuki customer records.
- **Duplicate container.** 886 rows / 885 numbers. Keep the newest complete row.
- **Outbound linkage.** Match by 计划单号, then real outbound no, then 关联OL, then container + customer. Orphan DS lines go to an exception file.

## Pilot

Pick 5–10 containers that are already devanned, have OL lines, preferably have outbound, and whose customer already exists. Skip HOLD on the first batch.

Reconcile pallet, carton, lbs, and cube per container against the source pivot. Pallet and carton must match exactly. Weight / cube may drift by at most 0.5% or 1 lb / 0.01 cube. Outbound cartons must not exceed on-hand.

Default sample mix if no list is provided: 2 simple single-location containers, 2 multi-location, 2 already outbound, 1 large carton count, 1 messy-remark but valid container number.

## Profile field map

Aligned with `backend/app/imports/profiles/west_coast_4_0.py`.

### OL → inbound

| Source | Target |
|---|---|
| 柜号 | container_number |
| 仓点 | fc_code |
| 库位 | location |
| 板数 | pallet_qty |
| 件数 | carton_qty |
| 磅数(lb) | weight_lbs |
| 体积 | cbm |
| 客户 | customer |
| 拆柜时间 | unload_date |
| 实际到仓时间 | received_date |
| FBA | fba_reference |
| PO | po_number |
| 备注 | remark |

Required: `container_number`, `fc_code`.

### DS → FBA

| Source | Target |
|---|---|
| 客户 | customer |
| 柜号 | container_number |
| ID / ST | st_number |
| FBA | shipment_id |
| PO | po_number |
| 件数 | carton_qty |
| LBS | weight_lbs |
| 体积 | cbm |
| 派送仓点 | amazon_fc_code |
| 备注 | remark |
| 关联OL | source_reference |

Required: `container_number`, `amazon_fc_code`.

### 出库 → outbound

| Source | Target |
|---|---|
| 计划单号 | ob_no |
| 仓点 | fc_code |
| ISA/预约编号 | appointment_reference |
| 预计送仓时间 | delivery_appointment_time |
| 出库时间 | actual_outbound_time |
| 真实板数 | completed_pallet_qty |
| 拣货单 | picking_reference |
| BOL | bol_reference |
| 预计体积 | planned_cbm |
| 预计板数 | planned_pallet_qty |
| 重量(lb) | planned_weight_lbs |
| 车队 | carrier |
| Redirect Code | redirect_code |
| 预计件数 | planned_carton_qty |
| POD | pod_reference |
| PO | po_number |
| FBA | fba_no |
| 真实件数 | completed_carton_qty |
| 真实重量 | completed_weight_lbs |
| 真实体积 | completed_cbm |
| 计划出库 | source_reference |

Required: `ob_no`, `fc_code`.

### Container Tracking (提柜)

Use `container_number`, `mbl_number`, `pod_eta`, `actual_delivery_at`, `wa_received_at`, `wa_complete_at`, `customer_reference`, `container_remark`, `source_row_number`. Dates as ISO-8601. Container numbers uppercase, no spaces.

## CSV templates

Empty UTF-8 headers live in `docs/import-templates/`.

## Limits

- Do not commit the 297 MB source workbook.
- Imports preview first; confirm writes in one transaction (`SKIP` duplicates by default).
- HOLD / exception `仓点` rows stay out of sellable inventory on the pilot.
