import argparse
import json
import time
import tracemalloc
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.imports.profiles import PROFILES
from app.imports.readers import file_sha256, workbook_metadata
from app.models import ImportJob, User, Warehouse
from app.services.phase8_import import stage_profile_job, validate_profile_job


def main() -> None:
    parser = argparse.ArgumentParser(description="PHASE 8 real workbook dry run")
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args()
    workbook = args.workbook.resolve()
    if not workbook.is_file():
        raise SystemExit("Workbook not found")
    tracemalloc.start()
    overall = time.perf_counter()
    digest = file_sha256(workbook)
    metadata = workbook_metadata(workbook)
    results = []
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "dlx001")) or db.scalar(select(User).order_by(User.id))
        warehouse = db.scalar(select(Warehouse).order_by(Warehouse.id))
        if user is None or warehouse is None:
            raise SystemExit("An admin user and warehouse are required")
        for profile in PROFILES.values():
            started = time.perf_counter()
            preview = stage_profile_job(
                db, path=workbook, original_name=workbook.name, file_hash=digest,
                file_size=workbook.stat().st_size, sheet_name=profile.sheet_name,
                profile_code=profile.code, warehouse_id=warehouse.id, user_id=user.id,
                sheet_names=metadata["sheet_names"], sheet_row_estimates=metadata["sheet_row_estimates"],
            )
            validation = validate_profile_job(db, db.get(ImportJob, preview.job_id), False)
            results.append({
                "profile": profile.code, "sheet": profile.sheet_name, "job_id": preview.job_id,
                "rows": validation.total_rows, "valid": validation.valid_rows,
                "warnings": validation.warning_rows, "errors": validation.error_rows,
                "mapping": preview.suggested_mapping,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "validation_seconds": validation.duration_seconds,
                "rows_per_second": validation.rows_per_second,
            })
    _, peak = tracemalloc.get_traced_memory()
    print(json.dumps({
        "mode": "DRY_RUN", "file_size": workbook.stat().st_size,
        "sheets": metadata, "results": results,
        "total_duration_seconds": round(time.perf_counter() - overall, 3),
        "python_peak_memory_mib": round(peak / 1024 / 1024, 2),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
