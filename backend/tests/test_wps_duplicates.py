from types import SimpleNamespace
from app.services.wps_duplicates import annotate_duplicates


def source(record="1"):
    return {"documentId": "doc", "sheetId": "sheet", "recordId": record}


def row(record="1", container=" TEST123 "):
    return {"sourceIdentity": source(record), "values": {"container_number": container}}


def existing(id=1, container="test123", metadata=None):
    return SimpleNamespace(id=id, container_number=container, source_metadata=metadata,
        inbound_no=f"IB-{id}", customer_id=id, warehouse_id=id, fc_code="ONT8",
        carton_qty=10, pallet_qty=1, raw_location_text="A01", status=1)


def check(rows, records, sheet="OL"):
    summary = annotate_duplicates([{"sheet": sheet, "rows": rows}], records)
    assert summary["importAllowed"] is False
    assert summary["inventoryBalanceChecked"] is False
    return [r["duplicateCheck"] for r in rows]


def test_history_candidates_include_other_customers_and_warehouses_and_limit():
    result = check([row()], [existing(i) for i in range(1, 13)])[0]
    assert result["status"] == "history_candidate"
    assert result["candidateCount"] == 12
    assert len(result["candidates"]) == 10
    assert result["candidates"][1]["warehouseId"] == 2
    assert result["candidates"][1]["customerId"] == 2


def test_exact_source_takes_precedence_and_conflicts_are_visible():
    linked = existing(2, "CHANGED", {"sourceIdentity": source()})
    result = check([row()], [existing(), linked])[0]
    assert result["status"] == "source_linked"
    assert [r["id"] for r in result["candidates"]] == [2]
    assert check([row()], [linked, existing(3, metadata={"sourceIdentity": source()})])[0]["status"] == "source_conflict"


def test_duplicate_missing_source_and_missing_container():
    assert all(r["status"] == "duplicate_source" for r in check([row(), row()], []))
    invalid = row()
    invalid["sourceIdentity"] = {}
    assert check([invalid], [existing()])[0]["status"] == "invalid_source"
    assert check([row(container="")], [existing()])[0]["status"] == "missing_container"
    assert check([row()], [], "提柜")[0]["status"] == "not_applicable"


def test_old_import_metadata_is_not_a_source_link():
    history = existing(metadata={"file": "doc", "sheet": "sheet", "row": "1"})
    assert check([row()], [history])[0]["status"] == "history_candidate"
    assert check([row(container="OTHER")], [history])[0]["status"] == "no_candidate"
