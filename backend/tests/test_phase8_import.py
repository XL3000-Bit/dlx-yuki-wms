from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.imports.profiles import detect_workbook, get_profile, suggest_profile
from app.imports.readers import file_sha256, row_fingerprint, stream_tabular, workbook_metadata
from app.models import FBAInventoryAllocation, FBAShipment, ImportJob, InboundRecord, InventoryLot, InventoryLotLocation, OutboundOrder
from app.services.phase8_import import confirm_profile_job, parse_date, split_locations, stage_profile_job, validate_profile_job


def make_book(path: Path, sheet: str, headers: list[str], rows: list[list[object]], other_rows: int = 0) -> Path:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    other = workbook.create_sheet("UNSELECTED")
    other.append(["Never Read"])
    for index in range(other_rows):
        other.append([index])
    workbook.save(path)
    return path


def stage(db: Session, seed, path: Path, profile_code: str, sheet: str, max_rows: int | None = None):
    metadata = workbook_metadata(path)
    preview = stage_profile_job(
        db, path=path, original_name=path.name, file_hash=file_sha256(path), file_size=path.stat().st_size,
        sheet_name=sheet, profile_code=profile_code, warehouse_id=seed["warehouse"].id,
        user_id=seed["admin"].id, sheet_names=metadata["sheet_names"],
        sheet_row_estimates=metadata["sheet_row_estimates"], batch_size=500, max_rows=max_rows,
    )
    return db.get(ImportJob, preview.job_id), preview


def test_profile_detection_and_fixed_mappings():
    sheets = ["提柜", "OL", "DS", "出库"]
    assert detect_workbook(sheets)
    assert suggest_profile("OL", sheets) == "WEST_COAST_4_0_OL"
    ol = get_profile("WEST_COAST_4_0_OL").mapping_for(["柜号", "仓点", "库位", "磅数(lb)", "未知列"])
    assert ol == {"柜号": "container_number", "仓点": "fc_code", "库位": "location", "磅数(lb)": "weight_lbs", "未知列": ""}
    ds = get_profile("WEST_COAST_4_0_DS").mapping_for(["ID", "FBA", "关联OL", "LBS"])
    assert ds == {"ID": "st_number", "FBA": "shipment_id", "关联OL": "source_reference", "LBS": "weight_lbs"}
    outbound = get_profile("WEST_COAST_4_0_OUTBOUND").mapping_for(["计划单号", "拣货单", "BOL", "重量(lb)", "预计重量"])
    assert outbound["拣货单"] == "picking_reference" and outbound["BOL"] == "bol_reference"
    assert outbound["重量(lb)"] == "planned_weight_lbs" and outbound["预计重量"] == ""


def test_streaming_selected_sheet_only_and_preview_limit(tmp_path: Path, db: Session, seed):
    path = make_book(tmp_path / "selected.xlsx", "OL", ["柜号", "仓点", "库位"], [[f"C{i}", "ONT8", "A01"] for i in range(80)], other_rows=500)
    headers, rows = stream_tabular(path, path.name, "OL")
    assert headers == ["柜号", "仓点", "库位"]
    assert sum(1 for _ in rows) == 80
    job, preview = stage(db, seed, path, "WEST_COAST_4_0_OL", "OL")
    assert job.total_rows == 80 and len(preview.preview_rows) == 30


def test_ol_multi_fc_multi_location_kg_fallback_and_progress(tmp_path: Path, db: Session, seed):
    path = make_book(tmp_path / "ol.xlsx", "OL",
                     ["柜号", "仓点", "库位", "板数", "件数", "重量(kg)", "磅数(lb)", "体积", "拆柜时间", "客户"],
                     [["CSNU5950921", "ABQ2", "G34-12P,G33-10P", 2, 20, 10, None, 1.5, "2026/08/01", "ACME"],
                      ["CSNU5950921", "FTW1", "A01", 3, 30, None, 100, 2, 46235, "ACME"]])
    job, _ = stage(db, seed, path, "WEST_COAST_4_0_OL", "OL")
    result = validate_profile_job(db, job)
    assert result.total_rows == 2 and result.error_rows == 0
    assert result.rows[0]["data"]["location_codes"] == ["G34-12P", "G33-10P"]
    assert result.rows[0]["data"]["weight_source"] == "KG_CONVERTED"
    assert result.rows[0]["data"]["weight_lbs"].startswith("22.046")
    assert parse_date(46235).isoformat() == "2026-08-01"
    assert job.current_stage == "READY" and float(job.progress_percent) == 100


def test_file_hash_row_fingerprint_and_duplicate_warning(tmp_path: Path, db: Session, seed):
    path = make_book(tmp_path / "duplicate.xlsx", "OL", ["柜号", "仓点"], [["DUP", "ONT8"], ["DUP", "ONT8"]])
    assert file_sha256(path) == file_sha256(path)
    assert row_fingerprint({"a": " X "}) == row_fingerprint({"a": "x"})
    job, _ = stage(db, seed, path, "WEST_COAST_4_0_OL", "OL")
    result = validate_profile_job(db, job)
    assert result.warning_rows == 2
    assert all(any(issue["code"] == "DUPLICATE_ROW" for issue in row["issues"]) for row in result.rows)


def test_large_batch_validation_and_error_export(tmp_path: Path, db: Session, seed, client: TestClient):
    path = make_book(tmp_path / "large.xlsx", "OL", ["柜号", "仓点", "板数"], [[f"LARGE{i}", "ONT8", i % 10] for i in range(2000)])
    job, _ = stage(db, seed, path, "WEST_COAST_4_0_OL", "OL")
    result = validate_profile_job(db, job, False)
    assert result.total_rows == 2000 and result.error_rows == 0 and result.rows_per_second > 0
    response = client.get(f"/api/v1/imports/{job.id}/errors.xlsx")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"


def test_location_split_normalizes_without_quantity_guessing():
    assert split_locations("G34-12P,\nG33-10P，g34-12p") == ["G34-12P", "G33-10P"]


def test_ol_confirm_trace_multi_location_and_idempotency(tmp_path: Path, db: Session, seed):
    path=make_book(tmp_path/"confirm-ol.xlsx","OL",["柜号","仓点","库位","板数","件数","磅数(lb)","体积","拆柜时间","PO"],[["TRACE1","ONT8","NEW-A,NEW-B",2,20,100,1,"2026/08/01","PO1"]])
    job,_=stage(db,seed,path,"WEST_COAST_4_0_OL","OL");assert validate_profile_job(db,job).error_rows==0
    result=confirm_profile_job(db,job,seed["admin"].id,auto_receive_to_inventory=True,auto_create_location=True)
    assert result.imported_rows==1 and result.reconciliation["database"]["counts"]["inventory_created"]==1
    inbound=db.query(InboundRecord).filter_by(container_number="TRACE1").one();lot=db.query(InventoryLot).filter_by(source_inbound_id=inbound.id).one()
    assert inbound.import_row_id and inbound.source_metadata["sheet"]=="OL" and lot.import_row_id==inbound.import_row_id
    locations=db.query(InventoryLotLocation).filter_by(inventory_lot_id=lot.id).all();assert len(locations)==2 and all(x.pallet_qty is None for x in locations)
    again,_=stage(db,seed,path,"WEST_COAST_4_0_OL","OL");validate_profile_job(db,again)
    assert again.duplicate_of_job_id==job.id


def test_outbound_external_references_do_not_generate_picking_or_bol(tmp_path: Path, db: Session, seed):
    path=make_book(tmp_path/"out.xlsx","出库",["计划单号","仓点","拣货单","BOL","PO"],[["EXT-OB-1","ONT8","EXTERNAL-PK","EXTERNAL-BOL","PO-LIST"]])
    job,_=stage(db,seed,path,"WEST_COAST_4_0_OUTBOUND","出库");validation=validate_profile_job(db,job);assert validation.error_rows==0
    result=confirm_profile_job(db,job,seed["admin"].id);assert result.imported_rows==1
    order=db.query(OutboundOrder).filter_by(ob_no="EXT-OB-1").one();assert order.picking_reference=="EXTERNAL-PK" and order.bol_reference=="EXTERNAL-BOL" and not order.allocations


def test_ds_inventory_match_grouping_and_ambiguous_inventory(tmp_path: Path, db: Session, seed):
    ol_path=make_book(tmp_path/"ds-source.xlsx","OL",["柜号","仓点","板数","件数","磅数(lb)","体积","拆柜时间"],[["DS-MATCH","ONT8",0,100,1000,10,"2026/08/01"]])
    ol_job,_=stage(db,seed,ol_path,"WEST_COAST_4_0_OL","OL");validate_profile_job(db,ol_job);confirm_profile_job(db,ol_job,seed["admin"].id,auto_receive_to_inventory=True)
    ds_path=make_book(tmp_path/"ds.xlsx","DS",["柜号","FBA","ID","件数","LBS","体积","派送仓点","关联OL"],[["DS-MATCH","FBA-EXT","ST-ONE",10,100,1,"ONT8","DS-MATCH-ONT8"],["DS-MATCH","FBA-EXT","ST-TWO",5,50,0.5,"ONT8","DS-MATCH-ONT8"]])
    ds_job,_=stage(db,seed,ds_path,"WEST_COAST_4_0_DS","DS");validation=validate_profile_job(db,ds_job);assert validation.error_rows==0
    result=confirm_profile_job(db,ds_job,seed["admin"].id);assert result.imported_rows==2
    assert db.query(FBAShipment).count()==1 and db.query(FBAInventoryAllocation).count()==1
    second_ol=make_book(tmp_path/"ds-source-2.xlsx","OL",["柜号","仓点","板数","件数","磅数(lb)","体积","拆柜时间"],[["DS-MATCH","ONT8",0,10,100,1,"2026/08/02"]])
    second_job,_=stage(db,seed,second_ol,"WEST_COAST_4_0_OL","OL");validate_profile_job(db,second_job);confirm_profile_job(db,second_job,seed["admin"].id,auto_receive_to_inventory=True)
    ambiguous_path=make_book(tmp_path/"ambiguous.xlsx","DS",["柜号","FBA","件数","LBS","体积","派送仓点"],[["DS-MATCH","FBA-AMB",1,1,0.1,"ONT8"]])
    ambiguous,_=stage(db,seed,ambiguous_path,"WEST_COAST_4_0_DS","DS");checked=validate_profile_job(db,ambiguous)
    assert checked.error_rows==1 and any(issue["code"]=="AMBIGUOUS_INVENTORY" for issue in checked.rows[0]["issues"])
