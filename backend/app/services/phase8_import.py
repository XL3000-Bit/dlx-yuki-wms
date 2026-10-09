from __future__ import annotations

from app.services.import_safety import BatchJournal, check_row, previous_rows

import time
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from openpyxl.utils.datetime import from_excel
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.imports.profiles import get_profile
from app.imports.readers import batched, row_fingerprint, stream_tabular
from app.models import (AmazonFCAddress, AuditLog, Customer, FBAInventoryAllocation, FBAShipment,
                        ImportError, ImportJob, ImportRow, InboundRecord, InventoryLot,
                        InventoryLotLocation, OutboundOrder, Warehouse, WarehouseArea, WarehouseLocation)
from app.models.import_job import ImportModule, ImportSeverity, ImportStatus, RowValidationStatus
from app.schemas.fba import AllocateRequest as FBAAllocateRequest, FBACreate
from app.schemas.imports import ImportSummary, PreviewResponse, ValidationSummary
from app.schemas.inbound import InboundCreate
from app.schemas.outbound import AllocateRequest as OutboundAllocateRequest, OBCreate
from app.services.fba import allocate as allocate_fba, create_fba
from app.services.inbound import create_inbound
from app.services.inventory import receive_inbound
from app.services.outbound import allocate as allocate_outbound, create_ob


ERROR_FIXES = {
    "MISSING_REQUIRED": "Fill the required source cell and upload again.",
    "INVALID_NUMBER": "Use a non-negative numeric value.",
    "INVALID_DATE": "Use YYYY-MM-DD, MM/DD/YYYY, YYYY/MM/DD, or a valid Excel date.",
    "UNKNOWN_WAREHOUSE": "Select an existing warehouse before validation.",
    "UNKNOWN_LOCATION": "Create the location or enable AUTO_CREATE_LOCATION during confirm.",
    "UNKNOWN_CUSTOMER": "Create or map the customer in master data.",
    "UNKNOWN_FC": "Add the Amazon FC address if shipping details are required.",
    "UNKNOWN_INVENTORY": "Import OL and receive inventory before importing DS or Outbound.",
    "AMBIGUOUS_INVENTORY": "Add a lot/source reference so exactly one inventory lot matches.",
    "OVER_ALLOCATION": "Reduce requested quantities to available inventory.",
    "DUPLICATE_ROW": "Remove the duplicate row or re-run with an explicit duplicate strategy.",
    "INVALID_WEIGHT_UNIT": "Populate LBS or confirm the source weight unit.",
}


def parse_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError("Invalid numeric value") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("Quantity cannot be negative")
    return result


def parse_date(value: Any) -> date | None:
    if value in (None, "", "-"):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 0:
        converted = from_excel(value)
        return converted.date() if isinstance(converted, datetime) else converted
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("Invalid date")


def split_locations(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    normalized = str(value).replace("\n", ",").replace("，", ",")
    return list(dict.fromkeys(part.strip().upper() for part in normalized.split(",") if part.strip()))


def stage_profile_job(
    db: Session, *, path: Path, original_name: str, file_hash: str, file_size: int,
    sheet_name: str, profile_code: str, warehouse_id: int, user_id: int,
    sheet_names: list[str], sheet_row_estimates: dict[str, int], batch_size: int = 1000,
    preview_limit: int = 30, max_rows: int | None = None,
    row_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> PreviewResponse:
    profile = get_profile(profile_code)
    if profile is None or profile.sheet_name != sheet_name:
        raise HTTPException(422, "Profile does not match selected sheet")
    if not 500 <= batch_size <= 5000:
        raise HTTPException(422, "batch_size must be between 500 and 5000")
    if db.get(Warehouse, warehouse_id) is None:
        raise HTTPException(422, "Warehouse not found")
    previous = db.scalar(select(ImportJob).where(
        ImportJob.file_hash == file_hash, ImportJob.module == profile.module,
        ImportJob.profile_code == profile.code, ImportJob.source_sheet == sheet_name,
        ImportJob.status == ImportStatus.COMPLETED,
    ).order_by(ImportJob.id.desc()))
    started = time.perf_counter()
    headers, rows = stream_tabular(path, original_name, sheet_name)
    mapping = profile.mapping_for(headers)
    missing = [target for target in profile.required_targets if target not in mapping.values()]
    if missing:
        raise HTTPException(422, f"Profile required columns not found: {', '.join(missing)}")
    job = ImportJob(
        module=profile.module, file_name=original_name, original_file_name=original_name,
        status=ImportStatus.READING, current_stage="READING", profile_code=profile.code,
        source_sheet=sheet_name, file_size=file_size, file_hash=file_hash,
        stored_file_path=str(path), batch_size=batch_size, mapping=mapping,
        detected_columns=headers, sheet_names=sheet_names, sheet_row_estimates=sheet_row_estimates,
        options={"warehouse_id": warehouse_id}, duplicate_of_job_id=previous.id if previous else None,
        created_by=user_id,
    )
    db.add(job)
    db.flush()
    preview: list[dict[str, Any]] = []
    total = 0
    fingerprint_fields = tuple(target for target in mapping.values() if target)
    for batch in batched(rows, batch_size):
        payload: list[dict[str, Any]] = []
        for row_number, raw in batch:
            if row_filter is not None and not row_filter(raw):
                continue
            if max_rows is not None and total + len(payload) >= max_rows:
                break
            mapped = {target: raw.get(source) for source, target in mapping.items() if target}
            fingerprint = row_fingerprint(mapped, fingerprint_fields)
            payload.append({"import_job_id": job.id, "row_number": row_number, "source_sheet": sheet_name,
                            "row_fingerprint": fingerprint, "raw_data": raw, "validation_status": RowValidationStatus.PENDING})
            if len(preview) < max(20, min(preview_limit, 50)):
                preview.append(raw)
        if not payload:
            continue
        db.execute(insert(ImportRow), payload)
        total += len(payload)
        job.processed_rows = total
        job.total_rows = total
        job.progress_percent = Decimal("100")
        db.flush()
        if max_rows is not None and total >= max_rows:
            break
    elapsed = time.perf_counter() - started
    job.status = ImportStatus.PREVIEWED
    job.current_stage = "MAPPING"
    job.performance = {"file_read_seconds": round(elapsed, 3), "read_rows_per_second": round(total / elapsed, 2) if elapsed else None}
    db.commit()
    return PreviewResponse(job_id=job.id, file_name=original_name, detected_columns=headers,
                           suggested_mapping=mapping, preview_rows=preview, total_rows=total)


def _lookup_casefold(rows: list[Any], *attrs: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows:
        for attr in attrs:
            value = getattr(row, attr, None)
            if value:
                result[str(value).strip().casefold()] = row
    return result


def validate_profile_job(db: Session, job: ImportJob, include_rows: bool = True) -> ValidationSummary:
    profile = get_profile(job.profile_code)
    if profile is None:
        raise HTTPException(409, "Import job does not use a PHASE 8 profile")
    if job.status not in (ImportStatus.PREVIEWED, ImportStatus.VALIDATED, ImportStatus.READY):
        raise HTTPException(409, "Import job cannot be validated in its current status")
    started = time.perf_counter()
    job.status = ImportStatus.VALIDATING
    job.current_stage = "VALIDATING"
    job.processed_rows = 0
    db.execute(delete(ImportError).where(ImportError.import_job_id == job.id))
    warehouse_id = int((job.options or {}).get("warehouse_id") or 0)
    warehouse = db.get(Warehouse, warehouse_id)
    customers = _lookup_casefold(list(db.scalars(select(Customer)).all()), "customer_code", "customer_name")
    locations = _lookup_casefold(list(db.scalars(select(WarehouseLocation).where(WarehouseLocation.warehouse_id == warehouse_id)).all()), "location_code")
    fc_codes = {str(value).upper() for value in db.scalars(select(AmazonFCAddress.fc_code)).all()}
    lots = list(db.scalars(select(InventoryLot).where(InventoryLot.warehouse_id == warehouse_id)).all())
    by_lot = {lot.lot_no.casefold(): [lot] for lot in lots}
    by_container: dict[str, list[InventoryLot]] = defaultdict(list)
    by_container_fc: dict[tuple[str, str], list[InventoryLot]] = defaultdict(list)
    for lot in lots:
        by_container[lot.container_number.casefold()].append(lot)
        by_container_fc[(lot.container_number.casefold(), (lot.fc_code or "").upper())].append(lot)
    fingerprint_counts = Counter(db.scalars(select(ImportRow.row_fingerprint).where(ImportRow.import_job_id == job.id)).all())
    requested_by_lot: dict[int, list[Decimal]] = defaultdict(lambda: [Decimal("0")] * 4)
    valid = warnings = errors = processed = 0
    output: list[dict[str, Any]] = []
    totals = defaultdict(Decimal)
    rows = db.scalars(select(ImportRow).where(ImportRow.import_job_id == job.id).order_by(ImportRow.row_number).execution_options(yield_per=job.batch_size))
    for row in rows:
        mapped = {target: row.raw_data.get(source) for source, target in (job.mapping or {}).items() if target}
        issues: list[tuple[ImportSeverity, str, str, str, Any]] = []
        def issue(severity: ImportSeverity, column: str, code: str, message: str, raw: Any = None) -> None:
            issues.append((severity, column, code, message, mapped.get(column) if raw is None else raw))
        if not warehouse:
            issue(ImportSeverity.ERROR, "warehouse", "UNKNOWN_WAREHOUSE", "Selected warehouse does not exist")
        if row.row_fingerprint and fingerprint_counts[row.row_fingerprint] > 1:
            issue(ImportSeverity.WARNING, "row", "DUPLICATE_ROW", "Duplicate normalized row exists in this sheet")
        customer_value = str(mapped.get("customer") or "").strip()
        customer = customers.get(customer_value.casefold()) if customer_value else None
        if customer_value and not customer:
            issue(ImportSeverity.WARNING, "customer", "UNKNOWN_CUSTOMER", "Customer does not exist")
        parsed: dict[str, Any] = {"warehouse_id": warehouse_id, "customer_id": customer.id if customer else None}
        for field in ('source_record_id', 'business_document_id', 'business_line_id'):
            if not str(mapped.get(field) or '').strip():
                issue(ImportSeverity.ERROR, field, 'SOURCE_IDENTITY_REQUIRED', 'Required stable source/document/detail identity is missing')
        if not customer:
            issue(ImportSeverity.ERROR, 'customer', 'OWNER_REQUIRED', 'An existing, unambiguous customer is required')
        mode = str(mapped.get('migration_mode') or 'HISTORICAL').strip().upper()
        parsed['migration_mode'] = mode
        if mode not in ('HISTORICAL', 'NEW_RECEIPT'):
            issue(ImportSeverity.ERROR, 'migration_mode', 'BALANCE_RECONCILIATION_REQUIRED', 'Opening balances require verified SKU, units and cutoff reconciliation; stock posting is not enabled')
        if profile.module != ImportModule.INBOUND:
            issue(ImportSeverity.ERROR, 'migration_mode', 'REMAINING_BUSINESS_UNVERIFIED', 'DS/Outbound migration is blocked until actual remaining business is reconciled')
        if mode == 'NEW_RECEIPT' and (mapped.get('received_date') or mapped.get('unload_date')):
            issue(ImportSeverity.ERROR, 'migration_mode', 'HISTORICAL_RECEIPT_CONFLICT', 'New receipt plan cannot contain actual arrival/unload dates')
        if profile.module == ImportModule.INBOUND:
            container = str(mapped.get("container_number") or "").strip().upper()
            fc = str(mapped.get("fc_code") or "").strip().upper()
            if not container: issue(ImportSeverity.ERROR, "container_number", "MISSING_REQUIRED", "Container number is required")
            if not fc: issue(ImportSeverity.ERROR, "fc_code", "MISSING_REQUIRED", "FC code is required")
            location_codes = split_locations(mapped.get("location"))
            unknown = [code for code in location_codes if code.casefold() not in locations]
            if unknown: issue(ImportSeverity.WARNING, "location", "UNKNOWN_LOCATION", f"Unknown location(s): {', '.join(unknown)}")
            parsed.update({"container_number": container, "fc_code": fc, "location_codes": location_codes,
                           "location_id": locations.get(location_codes[0].casefold()).id if location_codes and location_codes[0].casefold() in locations else None,
                           "raw_location_text": str(mapped.get("location") or "") or None})
            for field in ("unload_date", "received_date"):
                try: parsed[field] = parse_date(mapped.get(field))
                except ValueError: issue(ImportSeverity.ERROR, field, "INVALID_DATE", "Invalid date format"); parsed[field] = None
            for field in ("pallet_qty", "carton_qty", "weight_lbs", "cbm"):
                try: parsed[field] = parse_decimal(mapped.get(field))
                except ValueError: issue(ImportSeverity.ERROR, field, "INVALID_NUMBER", "Invalid numeric value"); parsed[field] = None
            parsed["weight_source"] = "LBS"
            if parsed.get("weight_lbs") is None and mapped.get("weight_kg") not in (None, "", 0, "0"):
                try:
                    kg = parse_decimal(mapped.get("weight_kg")); parsed["weight_lbs"] = kg * Decimal("2.2046226218") if kg is not None else None; parsed["weight_source"] = "KG_CONVERTED"
                except ValueError: issue(ImportSeverity.ERROR, "weight_kg", "INVALID_NUMBER", "Invalid KG weight")
        elif profile.module == ImportModule.FBA:
            container = str(mapped.get("container_number") or "").strip().upper()
            fc = str(mapped.get("amazon_fc_code") or "").strip().upper()
            if not container: issue(ImportSeverity.ERROR, "container_number", "MISSING_REQUIRED", "Container number is required")
            if not fc: issue(ImportSeverity.ERROR, "amazon_fc_code", "MISSING_REQUIRED", "Amazon FC is required")
            if fc and fc not in fc_codes: issue(ImportSeverity.WARNING, "amazon_fc_code", "UNKNOWN_FC", "Amazon FC address is not configured")
            candidates = by_container_fc.get((container.casefold(), fc), []) or by_container.get(container.casefold(), [])
            source = str(mapped.get("source_reference") or "").strip()
            if source and "-" in source:
                source_container, source_fc = source.rsplit("-", 1)
                candidates = by_container_fc.get((source_container.casefold(), source_fc.upper()), []) or candidates
            if not candidates: issue(ImportSeverity.ERROR, "container_number", "UNKNOWN_INVENTORY", "No inventory lot matches DS row")
            elif len(candidates) > 1: issue(ImportSeverity.ERROR, "container_number", "AMBIGUOUS_INVENTORY", "Multiple inventory lots match DS row")
            parsed.update({"container_number": container, "amazon_fc_code": fc, "inventory_lot_id": candidates[0].id if len(candidates) == 1 else None})
            for field in ("carton_qty", "weight_lbs", "cbm"):
                try: parsed[field] = parse_decimal(mapped.get(field)) or Decimal("0")
                except ValueError: issue(ImportSeverity.ERROR, field, "INVALID_NUMBER", "Invalid numeric value"); parsed[field] = Decimal("0")
            parsed["pallet_qty"] = Decimal("0")
            if parsed["weight_lbs"] == 0 and mapped.get("weight_unknown_unit") not in (None, "", 0, "0"):
                issue(ImportSeverity.WARNING, "weight_unknown_unit", "INVALID_WEIGHT_UNIT", "Weight column unit is unknown; LBS was not populated")
            if len(candidates) == 1:
                lot = candidates[0]
                requested = (parsed["pallet_qty"], parsed["carton_qty"], parsed["weight_lbs"], parsed["cbm"])
                available = (lot.available_pallet_qty, lot.available_carton_qty, lot.available_weight_lbs, lot.available_cbm)
                cumulative = requested_by_lot[lot.id]
                for index, value in enumerate(requested): cumulative[index] += value
                if any(req > have for req, have in zip(cumulative, available)):
                    issue(ImportSeverity.ERROR, "carton_qty", "OVER_ALLOCATION", "DS request exceeds available inventory")
        else:
            ob_no = str(mapped.get("ob_no") or "").strip()
            fc = str(mapped.get("fc_code") or "").strip().upper()
            if not ob_no: issue(ImportSeverity.ERROR, "ob_no", "MISSING_REQUIRED", "Outbound reference is required")
            if not fc: issue(ImportSeverity.ERROR, "fc_code", "MISSING_REQUIRED", "FC code is required")
            parsed.update({"ob_no": ob_no, "fc_code": fc})
            for field in ("planned_pallet_qty", "planned_carton_qty", "planned_weight_lbs", "planned_cbm", "completed_pallet_qty", "completed_carton_qty", "completed_weight_lbs", "completed_cbm"):
                try: parsed[field] = parse_decimal(mapped.get(field)) or Decimal("0")
                except ValueError: issue(ImportSeverity.ERROR, field, "INVALID_NUMBER", "Invalid numeric value"); parsed[field] = Decimal("0")
            try: parsed["delivery_appointment_time"] = parse_date(mapped.get("delivery_appointment_time"))
            except ValueError: issue(ImportSeverity.ERROR, "delivery_appointment_time", "INVALID_DATE", "Invalid appointment date")
            references = [part.strip() for part in str(mapped.get("source_reference") or "").replace("，", ",").split(",") if part.strip()]
            matched: list[int] = []
            for reference in references:
                if "-" in reference:
                    cntr, ref_fc = reference.rsplit("-", 1); candidates = by_container_fc.get((cntr.casefold(), ref_fc.upper()), [])
                else: candidates = by_container.get(reference.casefold(), [])
                if len(candidates) == 1: matched.append(candidates[0].id)
                elif len(candidates) > 1: issue(ImportSeverity.ERROR, "source_reference", "AMBIGUOUS_INVENTORY", f"Multiple lots match {reference}")
            parsed["inventory_lot_ids"] = list(dict.fromkeys(matched))
            fba_value=str(mapped.get("fba_no")or"").strip();fba=db.scalar(select(FBAShipment).where(or_(FBAShipment.fba_no==fba_value,FBAShipment.shipment_id==fba_value))) if fba_value else None
            parsed["fba_shipment_id"]=fba.id if fba else None;parsed["fba_allocation_id"]=None
            if len(parsed["inventory_lot_ids"])==1:
                lot_id=parsed["inventory_lot_ids"][0];source_limits=None
                if fba:
                    fba_allocation=db.scalar(select(FBAInventoryAllocation).where(FBAInventoryAllocation.fba_shipment_id==fba.id,FBAInventoryAllocation.inventory_lot_id==lot_id));parsed["fba_allocation_id"]=fba_allocation.id if fba_allocation else None
                    if fba_allocation:source_limits=(fba_allocation.allocated_pallet_qty,fba_allocation.allocated_carton_qty,fba_allocation.allocated_weight_lbs,fba_allocation.allocated_cbm)
                else:
                    lot=db.get(InventoryLot,lot_id);source_limits=(lot.available_pallet_qty,lot.available_carton_qty,lot.available_weight_lbs,lot.available_cbm) if lot else None
                requested=(parsed["planned_pallet_qty"],parsed["planned_carton_qty"],parsed["planned_weight_lbs"],parsed["planned_cbm"])
                if source_limits and any(req>limit for req,limit in zip(requested,source_limits)):issue(ImportSeverity.ERROR,"planned_pallet_qty","OVER_ALLOCATION","Outbound request exceeds matched inventory")
        for key in ("pallet_qty", "carton_qty", "weight_lbs", "cbm", "planned_pallet_qty", "planned_carton_qty", "planned_weight_lbs", "planned_cbm", "completed_pallet_qty", "completed_carton_qty", "completed_weight_lbs", "completed_cbm"):
            value = parsed.get(key)
            if isinstance(value, Decimal): totals[key] += value
        for severity, column, code, message, raw in issues:
            db.add(ImportError(import_job_id=job.id, row_number=row.row_number, column_name=column,
                               raw_value=None if raw is None else str(raw), severity=severity,
                               error_code=code, error_message=message, suggested_fix=ERROR_FIXES.get(code)))
        has_error = any(item[0] == ImportSeverity.ERROR for item in issues)
        has_warning = any(item[0] == ImportSeverity.WARNING for item in issues)
        row.validation_status = RowValidationStatus.ERROR if has_error else RowValidationStatus.WARNING if has_warning else RowValidationStatus.VALID
        row.mapped_data = {**mapped, **{key: value.isoformat() if isinstance(value, date) else str(value) if isinstance(value, Decimal) else value for key, value in parsed.items()}}
        errors += int(has_error); warnings += int(has_warning and not has_error); valid += int(not has_error); processed += 1
        if include_rows and len(output) < 50:
            output.append({"row_number": row.row_number, "data": row.mapped_data, "status": row.validation_status.value,
                           "issues": [{"severity": item[0].value, "column": item[1], "code": item[2], "message": item[3]} for item in issues]})
        if processed % job.batch_size == 0:
            job.processed_rows = processed; job.progress_percent = Decimal(processed * 100) / max(job.total_rows, 1); db.flush()
    elapsed = time.perf_counter() - started
    job.processed_rows = processed; job.progress_percent = Decimal("100"); job.valid_rows = valid; job.warning_rows = warnings; job.error_rows = errors
    job.status = ImportStatus.READY; job.current_stage = "READY"
    job.reconciliation = {"excel": {key: str(value) for key, value in totals.items()}}
    performance = dict(job.performance or {}); performance.update({"validation_seconds": round(elapsed, 3), "validation_rows_per_second": round(processed / elapsed, 2) if elapsed else None}); job.performance = performance
    db.commit()
    return ValidationSummary(job_id=job.id, total_rows=job.total_rows, valid_rows=valid, warning_rows=warnings,
                             error_rows=errors, rows=output, duration_seconds=round(elapsed, 3),
                             rows_per_second=round(processed / elapsed, 2) if elapsed else None)


def _decimal_or_zero(value: Any) -> Decimal:
    return parse_decimal(value) or Decimal("0")


def confirm_profile_job(db: Session, job: ImportJob, user_id: int, *, duplicate_strategy: str = "SKIP",
                        include_warning_rows: bool = True, auto_receive_to_inventory: bool = False,
                        auto_create_location: bool = False) -> ImportSummary:
    profile = get_profile(job.profile_code)
    if profile is None:
        raise HTTPException(409, "Import job does not use a PHASE 8 profile")
    if job.status not in (ImportStatus.READY, ImportStatus.VALIDATED):
        raise HTTPException(409, "Validate the import job before confirm")
    if auto_receive_to_inventory:
        raise HTTPException(409, 'HISTORICAL_STOCK_BLOCKED: import never performs receipt; reconcile opening stock separately')
    if profile.module != ImportModule.INBOUND:
        raise HTTPException(409, 'REMAINING_BUSINESS_UNVERIFIED: DS/Outbound migration is not enabled')
    sources, businesses = previous_rows(db, job)
    # Serialize confirmation of this batch as well as identities in the warehouse.
    db.refresh(job, with_for_update=True)
    if job.status not in (ImportStatus.READY, ImportStatus.VALIDATED):
        raise HTTPException(409, 'Batch already processed')
    started = time.perf_counter();job.status=ImportStatus.IMPORTING;job.current_stage="IMPORTING";job.processed_rows=0;db.flush()
    imported=skipped=created_inbound=updated_inbound=created_inventory=created_fba=created_allocations=created_outbound=0;imported_totals=defaultdict(Decimal)
    warehouse_id=int((job.options or {}).get("warehouse_id") or 0);warehouse=db.get(Warehouse,warehouse_id)
    if warehouse is None:raise HTTPException(422,"Warehouse not found")
    locations={location.location_code.casefold():location for location in db.scalars(select(WarehouseLocation).where(WarehouseLocation.warehouse_id==warehouse_id)).all()}
    area=db.scalar(select(WarehouseArea).where(WarehouseArea.warehouse_id==warehouse_id).order_by(WarehouseArea.id))
    rows=db.scalars(select(ImportRow).where(ImportRow.import_job_id==job.id).order_by(ImportRow.row_number).execution_options(yield_per=job.batch_size))
    journal = BatchJournal(db)
    try:
        groups:dict[str,Any]={}
        for row in rows:
            if row.validation_status==RowValidationStatus.ERROR or (row.validation_status==RowValidationStatus.WARNING and not include_warning_rows):skipped+=1;continue
            data=dict(row.mapped_data or {})
            marker, prior, identical = check_row(data, job, sources, businesses, duplicate_strategy)
            mode = data.get('migration_mode') or 'HISTORICAL'
            if mode not in ('HISTORICAL', 'NEW_RECEIPT') or (mode == 'NEW_RECEIPT' and (data.get('received_date') or data.get('unload_date'))):
                raise HTTPException(409, 'HISTORICAL_STOCK_BLOCKED: invalid receipt mode')
            data['_identity'] = marker
            if prior: data['_previous_row_id'] = prior.id
            row.mapped_data = data
            if identical:
                row.validation_status=RowValidationStatus.SKIPPED;skipped+=1;continue
            sources[tuple(marker['source'])]=row;businesses[tuple(marker['business'])]=row
            if profile.module==ImportModule.INBOUND:
                location_codes=list(data.get("location_codes")or[]);location=None
                if location_codes:
                    for code in location_codes:
                        current=locations.get(code.casefold())
                        if current is None and auto_create_location:
                            if area is None:raise HTTPException(422,"Warehouse requires an area before AUTO_CREATE_LOCATION")
                            current=WarehouseLocation(warehouse_id=warehouse_id,area_id=area.id,location_code=code,location_name=code);db.add(current);db.flush();locations[code.casefold()]=current;db.add(AuditLog(user_id=user_id,action="IMPORT_AUTO_CREATE_LOCATION",entity_type="LOCATION",entity_id=current.id,after_data={"import_job_id":job.id,"code":code}))
                        if location is None and current is not None:location=current
                received=parse_date(data.get("received_date"));unload=parse_date(data.get("unload_date"));stable=received or unload
                existing=db.scalar(select(InboundRecord).where(InboundRecord.id==prior.created_entity_id).with_for_update().execution_options(populate_existing=True)) if prior else None
                if prior and (existing is None or existing.status != 0 or db.scalar(select(InventoryLot.id).where(InventoryLot.source_inbound_id==existing.id))):
                    raise HTTPException(409, 'UPDATE_HAS_DEPENDENCIES: only pristine draft documents can be revised')
                if existing and (existing.source_metadata or {}).get('migration_mode') != mode:
                    raise HTTPException(409, 'MIGRATION_MODE_IMMUTABLE: history cannot be converted to new receipts')
                payload=InboundCreate(container_number=data["container_number"],customer_id=data.get("customer_id"),warehouse_id=warehouse_id,unload_date=unload,received_date=received,fc_code=data.get("fc_code"),pallet_qty=_decimal_or_zero(data.get("pallet_qty")),carton_qty=_decimal_or_zero(data.get("carton_qty")),weight_lbs=parse_decimal(data.get("weight_lbs")),cbm=parse_decimal(data.get("cbm")),location_id=location.id if location else None,status=3 if auto_receive_to_inventory and stable else 0,remark=str(data.get("remark")or"")or None)
                if existing:
                    for key,value in payload.model_dump().items():setattr(existing,key,value)
                    entity=existing;updated_inbound+=1
                else:entity=create_inbound(db,payload,user_id,job.id,False);created_inbound+=1
                entity.raw_location_text=data.get("raw_location_text");entity.po_number=str(data.get("po_number")or"")or None;entity.fba_reference=str(data.get("fba_reference")or"")or None;entity.weight_source=data.get("weight_source");entity.import_row_id=row.id;entity.source_metadata={"file":job.original_file_name,"sheet":job.source_sheet,"row":row.row_number,"raw":row.raw_data,"migration_mode":mode,"source_record_id":data["source_record_id"]}
                db.flush()
                if auto_receive_to_inventory and stable and not db.scalar(select(InventoryLot.id).where(InventoryLot.source_inbound_id==entity.id)):
                    lot=receive_inbound(db,entity.id,user_id,False);created_inventory+=1
                    for code in location_codes:
                        loc=locations.get(code.casefold())
                        if loc:db.add(InventoryLotLocation(inventory_lot_id=lot.id,location_id=loc.id,pallet_qty=lot.original_pallet_qty if len(location_codes)==1 else None,carton_qty=lot.original_carton_qty if len(location_codes)==1 else None))
                row.created_entity_type="INBOUND";row.created_entity_id=entity.id;created_inbound+=0
            elif profile.module==ImportModule.FBA:
                requested=(_decimal_or_zero(data.get("pallet_qty")),_decimal_or_zero(data.get("carton_qty")),_decimal_or_zero(data.get("weight_lbs")),_decimal_or_zero(data.get("cbm")));locked_lot=db.scalar(select(InventoryLot).where(InventoryLot.id==int(data["inventory_lot_id"])).with_for_update());available=(locked_lot.available_pallet_qty,locked_lot.available_carton_qty,locked_lot.available_weight_lbs,locked_lot.available_cbm) if locked_lot else (Decimal("0"),)*4
                if any(req>have for req,have in zip(requested,available)):
                    row.validation_status=RowValidationStatus.ERROR;db.add(ImportError(import_job_id=job.id,row_number=row.row_number,column_name="carton_qty",severity=ImportSeverity.ERROR,error_code="OVER_ALLOCATION",error_message="Locked inventory balance is lower than the validated request",suggested_fix=ERROR_FIXES["OVER_ALLOCATION"]));job.error_rows+=1;skipped+=1;continue
                group=str(data.get("shipment_id")or data.get("st_number")or f"FBA{datetime.now():%y%m%d}{row.row_number:04d}").strip();shipment=groups.get(group)
                if shipment is None:
                    shipment=db.scalar(select(FBAShipment).where(FBAShipment.shipment_id==str(data.get("shipment_id")or"").strip())) if data.get("shipment_id") else None
                    if shipment is None:
                        shipment=create_fba(db,FBACreate(customer_id=data.get("customer_id"),warehouse_id=warehouse_id,amazon_fc_code=data.get("amazon_fc_code"),shipment_id=str(data.get("shipment_id")or"")or None,st_number=str(data.get("st_number")or"")or None,reference_no=str(data.get("source_reference")or"")or None,remark=str(data.get("remark")or"")or None),user_id,None,False);shipment.po_number=str(data.get("po_number")or"")or None;shipment.source_reference=str(data.get("source_reference")or"")or None;shipment.import_job_id=job.id;created_fba+=1
                    groups[group]=shipment
                allocation=allocate_fba(db,shipment.id,FBAAllocateRequest(inventory_lot_id=int(data["inventory_lot_id"]),pallet_qty=requested[0],carton_qty=requested[1],weight_lbs=requested[2],cbm=requested[3],confirm_fc_mismatch=False),user_id,False);allocation.import_row_id=row.id;created_allocations+=1;row.created_entity_type="FBA";row.created_entity_id=shipment.id
            else:
                supplied=str(data.get("ob_no")or"").strip();order=db.scalar(select(OutboundOrder).where(OutboundOrder.ob_no==supplied)) if supplied else None
                if order and order.status==5:row.validation_status=RowValidationStatus.SKIPPED;skipped+=1;continue
                if order and duplicate_strategy=="SKIP":row.validation_status=RowValidationStatus.SKIPPED;skipped+=1;continue
                if order is None:
                    fba_value=str(data.get("fba_no")or"").strip();fba=db.scalar(select(FBAShipment).where(or_(FBAShipment.fba_no==fba_value,FBAShipment.shipment_id==fba_value))) if fba_value else None
                    order=create_ob(db,OBCreate(warehouse_id=warehouse_id,customer_id=data.get("customer_id"),carrier_id=None,fba_shipment_id=fba.id if fba else None,ob_type="FBA" if fba else "STANDARD",fc_code=data.get("fc_code"),reference_no=supplied),user_id,supplied or None,False);created_outbound+=1
                order.appointment_reference=str(data.get("appointment_reference")or"")or None;order.picking_reference=str(data.get("picking_reference")or"")or None;order.bol_reference=str(data.get("bol_reference")or"")or None;order.redirect_code=str(data.get("redirect_code")or"")or None;order.pod_reference=str(data.get("pod_reference")or"")or None;order.po_number=str(data.get("po_number")or"")or None;order.import_job_id=job.id
                lot_ids=list(data.get("inventory_lot_ids")or[])
                if len(lot_ids)==1:
                    pallet=_decimal_or_zero(data.get("planned_pallet_qty"));carton=_decimal_or_zero(data.get("planned_carton_qty"));weight=_decimal_or_zero(data.get("planned_weight_lbs"));cbm=_decimal_or_zero(data.get("planned_cbm"))
                    if any((pallet,carton,weight,cbm)):
                        allocation=allocate_outbound(db,order.id,OutboundAllocateRequest(inventory_lot_id=lot_ids[0],fba_allocation_id=data.get("fba_allocation_id"),pallet_qty=pallet,carton_qty=carton,weight_lbs=weight,cbm=cbm),user_id,False);allocation.import_row_id=row.id;created_allocations+=1
                row.created_entity_type="OUTBOUND";row.created_entity_id=order.id
            row.validation_status=RowValidationStatus.IMPORTED;imported+=1
            total_fields=("pallet_qty","carton_qty","weight_lbs","cbm") if profile.module!=ImportModule.OUTBOUND else ("planned_pallet_qty","planned_carton_qty","planned_weight_lbs","planned_cbm","completed_pallet_qty","completed_carton_qty","completed_weight_lbs","completed_cbm")
            for field in total_fields:imported_totals[field]+=_decimal_or_zero(data.get(field))
            if imported%job.batch_size==0:job.processed_rows=imported+skipped;job.progress_percent=Decimal(job.processed_rows*100)/max(job.total_rows,1);db.flush()
        job.imported_rows=imported;job.status=ImportStatus.COMPLETED;job.current_stage="COMPLETED";job.processed_rows=job.total_rows;job.progress_percent=Decimal("100");job.completed_at=datetime.now()
        counts={"inbound_created":created_inbound,"inbound_updated":updated_inbound,"inventory_created":created_inventory,"fba_created":created_fba,"outbound_created":created_outbound,"allocations_created":created_allocations,"skipped":skipped};excel_totals=(job.reconciliation or{}).get("excel",{});database_totals={key:str(value) for key,value in imported_totals.items()};differences={key:str(Decimal(str(excel_totals.get(key)or 0))-Decimal(str(database_totals.get(key)or 0))) for key in set(excel_totals)|set(database_totals)}
        job.reconciliation={"excel":excel_totals,"database":{"counts":counts,"totals":database_totals},"difference":differences};elapsed=time.perf_counter()-started;perf=dict(job.performance or{});perf.update({"db_write_seconds":round(elapsed,3),"db_rows_per_second":round(imported/elapsed,2)if elapsed else None,"total_duration_seconds":round(sum(float(perf.get(key)or 0)for key in("file_read_seconds","validation_seconds"))+elapsed,3)});job.performance=perf;db.add(AuditLog(user_id=user_id,action=f"IMPORT_{profile.code}",entity_type="IMPORT_JOB",entity_id=job.id,after_data=counts));job.options={**(job.options or {}), "migration_journal":journal.finish()};db.commit()
    except Exception as exc:
        failed_job_id=job.id
        failed_row_number=row.row_number if 'row' in locals() else 0
        detail=str(exc.detail) if isinstance(exc, HTTPException) else 'Import transaction failed'
        db.rollback();failed=db.get(ImportJob,failed_job_id)
        if failed:
            failed.status=ImportStatus.FAILED;failed.current_stage="FAILED"
            db.add(ImportError(import_job_id=failed.id,row_number=failed_row_number,
                column_name="source_record_id",severity=ImportSeverity.ERROR,
                error_code="IMPORT_CONFLICT",error_message=detail,
                suggested_fix="Resolve the reported identity/revision conflict, then validate a new batch."))
            db.commit()
        raise
    finally:
        journal.close()
    return ImportSummary(job_id=job.id,total_rows=job.total_rows,imported_rows=imported,skipped_rows=skipped,warning_rows=job.warning_rows,error_rows=job.error_rows,reconciliation=job.reconciliation)
