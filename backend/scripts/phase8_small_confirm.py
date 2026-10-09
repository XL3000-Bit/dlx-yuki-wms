import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.imports.profiles import get_profile
from app.imports.readers import file_sha256, stream_tabular, workbook_metadata
from app.models import ImportJob, User, Warehouse
from app.services.phase8_import import confirm_profile_job, stage_profile_job, validate_profile_job


def selected_rows(path: Path, sheet: str, profile_code: str, limit: int):
    profile = get_profile(profile_code)
    headers, rows = stream_tabular(path, path.name, sheet)
    mapping = profile.mapping_for(headers)
    output = []
    for _, raw in rows:
        output.append({target: raw.get(source) for source, target in mapping.items() if target})
        if len(output) >= limit:
            break
    return output


def source_key(value: object):
    text = str(value or "").strip()
    if "-" not in text:
        return None
    container, fc = text.rsplit("-", 1)
    return container.strip().upper(), fc.strip().upper()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args()
    path = args.workbook.resolve();metadata = workbook_metadata(path);digest = file_sha256(path)
    ds_rows = selected_rows(path, "DS", "WEST_COAST_4_0_DS", 100)
    outbound_rows = selected_rows(path, "出库", "WEST_COAST_4_0_OUTBOUND", 50)
    targets = {key for row in ds_rows if (key := source_key(row.get("source_reference")))}
    for row in outbound_rows:
        for value in str(row.get("source_reference") or "").replace("，", ",").split(","):
            if key := source_key(value): targets.add(key)
    ol_profile = get_profile("WEST_COAST_4_0_OL")
    ol_headers, _ = stream_tabular(path, path.name, "OL")
    ol_mapping = ol_profile.mapping_for(ol_headers)
    first_seen = {"count": 0}
    def ol_filter(raw):
        mapped = {target: raw.get(source) for source, target in ol_mapping.items() if target}
        key = (str(mapped.get("container_number") or "").strip().upper(), str(mapped.get("fc_code") or "").strip().upper())
        take = first_seen["count"] < 100 or key in targets
        first_seen["count"] += 1
        return take
    results = {}
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "dlx001"));warehouse = db.scalar(select(Warehouse).where(Warehouse.warehouse_code == "PHASE8-DEV"))
        if user is None or warehouse is None: raise SystemExit("PHASE 8 development fixtures are missing")
        common = dict(db=db, path=path, original_name=path.name, file_hash=digest, file_size=path.stat().st_size,
                      warehouse_id=warehouse.id, user_id=user.id, sheet_names=metadata["sheet_names"], sheet_row_estimates=metadata["sheet_row_estimates"], batch_size=500)
        existing_ol=db.scalar(select(ImportJob).where(ImportJob.file_hash==digest,ImportJob.profile_code=="WEST_COAST_4_0_OL",ImportJob.status=="COMPLETED").order_by(ImportJob.id.desc()))
        if existing_ol:
            results["OL"]={"job_id":existing_ol.id,"reused_completed_job":True,"confirm":existing_ol.reconciliation}
        else:
            ol_preview = stage_profile_job(**common, sheet_name="OL", profile_code="WEST_COAST_4_0_OL", row_filter=ol_filter)
            ol_job = db.get(ImportJob, ol_preview.job_id);ol_validation = validate_profile_job(db, ol_job, False)
            ol_result = confirm_profile_job(db, ol_job, user.id, auto_receive_to_inventory=True, auto_create_location=True)
            results["OL"] = {"job_id": ol_job.id, "validation": ol_validation.model_dump(exclude={"rows"}), "confirm": ol_result.model_dump()}

        existing_ds=db.scalar(select(ImportJob).where(ImportJob.file_hash==digest,ImportJob.profile_code=="WEST_COAST_4_0_DS",ImportJob.status=="COMPLETED").order_by(ImportJob.id.desc()))
        if existing_ds:
            results["DS"]={"job_id":existing_ds.id,"reused_completed_job":True,"confirm":existing_ds.reconciliation}
        else:
            ds_preview = stage_profile_job(**common, sheet_name="DS", profile_code="WEST_COAST_4_0_DS", max_rows=100)
            ds_job = db.get(ImportJob, ds_preview.job_id);ds_validation = validate_profile_job(db, ds_job, False)
            ds_result = confirm_profile_job(db, ds_job, user.id)
            results["DS"] = {"job_id": ds_job.id, "validation": ds_validation.model_dump(exclude={"rows"}), "confirm": ds_result.model_dump()}

        out_preview = stage_profile_job(**common, sheet_name="出库", profile_code="WEST_COAST_4_0_OUTBOUND", max_rows=50)
        out_job = db.get(ImportJob, out_preview.job_id);out_validation = validate_profile_job(db, out_job, False)
        out_result = confirm_profile_job(db, out_job, user.id)
        results["OUTBOUND"] = {"job_id": out_job.id, "validation": out_validation.model_dump(exclude={"rows"}), "confirm": out_result.model_dump()}
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__": main()
