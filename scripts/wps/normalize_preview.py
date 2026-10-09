"""Normalize all-customer WPS samples locally; never import or modify inventory."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from pull_preview import PreviewError

NUMBERS = {"板数": "pallet_qty", "件数": "carton_qty", "磅数(lb)": "weight_lbs",
           "重量(kg)": "weight_kg", "体积": "cbm"}
DATES = {"拆柜时间": "unload_date", "实际到仓时间": "received_date",
         "库位更新时间": "location_updated_date", "ETA": "eta",
         "预计到仓时间": "expected_arrival_date", "实际到仓日期": "received_date",
         "完成拆柜日期": "unload_date"}


def normalize(snapshot: dict) -> dict:
    if snapshot.get("source") != "wps_airscript" or snapshot.get("mode") != "preview_only":
        raise PreviewError("Expected a WPS preview")
    if snapshot.get("sheet") not in ("OL", "提柜"):
        raise PreviewError("Only OL and inbound container previews are supported")
    if not isinstance(snapshot.get("records"), list):
        raise PreviewError("Invalid records")
    rows, seen = [], set()
    for record in snapshot["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
            raise PreviewError("Missing record identity")
        if record["id"] in seen:
            raise PreviewError("Duplicate record identity")
        seen.add(record["id"])
        raw = record.get("fields")
        if not isinstance(raw, dict):
            raise PreviewError("Invalid record fields")
        issues = []

        def issue(field, code):
            issues.append({"field": field, "code": code})

        def single(field):
            value = raw.get(field)
            if isinstance(value, list):
                if len(value) > 1:
                    issue(field, "multiple_values")
                    return None
                value = value[0] if value else None
            if isinstance(value, (dict, list, bool)):
                issue(field, "unsupported_value")
                return None
            return None if value is None or str(value).strip() in ("", "-") else str(value).strip()

        values = {"customer": single("客户"), "container_number": single("柜号"),
                  "remark": single("备注")}
        for field, key in (("客户", "customer"), ("柜号", "container_number")):
            if not values[key]:
                issue(field, "missing_or_ambiguous")
        for field, key in NUMBERS.items():
            if field not in snapshot.get("fields", []):
                continue
            value = single(field)
            values[key] = None
            if value is not None:
                try:
                    number = Decimal(value.replace(",", ""))
                    if not number.is_finite() or number < 0:
                        raise InvalidOperation
                    # Decimal strings retain precision and distinguish null from zero.
                    values[key] = str(number)
                except InvalidOperation:
                    issue(field, "invalid_number")
        for field, key in DATES.items():
            if field not in snapshot.get("fields", []):
                continue
            value = single(field)
            values[key] = None
            if value:
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S",
                            "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
                    try:
                        values[key] = datetime.strptime(value, fmt).isoformat() if "%H" in fmt else datetime.strptime(value, fmt).date().isoformat()
                        break
                    except ValueError:
                        pass
                if values[key] is None:
                    issue(field, "invalid_date")
        if snapshot["sheet"] == "OL":
            values["raw_location_text"] = raw.get("库位")
            location = single("库位")
            values["location_candidates"] = list(dict.fromkeys(
                part.strip().upper() for part in re.split(r"[,，\r\n]+", location or "") if part.strip()))
            if not location:
                issue("库位", "missing_or_ambiguous")
            if any(re.search(r"-\d+P$", part, re.I) for part in values["location_candidates"]):
                issue("库位", "pallet_suffix_needs_review")
            destination = single("仓点")
            values["destination"] = destination
            values["destination_kind"] = {"HOLD": "hold", "客户自提": "customer_pickup", "FEDEX": "carrier"}.get(
                (destination or "").upper(), "unverified")
            if values["destination_kind"] == "unverified":
                issue("仓点", "destination_needs_mapping")
            for field, key in (("FBA", "fba_references"), ("PO", "po_numbers")):
                value = raw.get(field)
                values[key] = value if isinstance(value, list) else ([] if value is None or value == "" else [value])
            if values.get("weight_lbs") == "0" or values.get("weight_kg") == "0":
                issue("weight", "zero_weight_needs_review")
        else:
            for field, key in (("船司", "carrier"), ("MBL", "mbl"), ("状态", "status"), ("柜型", "container_type")):
                values[key] = single(field)
        identity = {"documentId": snapshot.get("documentId"), "sheetId": snapshot.get("sheetId"),
                    "recordId": record["id"]}
        if any(value is None or value == "" for value in identity.values()):
            issue("source", "incomplete_identity")
        rows.append({"sourceIdentity": identity, "customerMatchStatus": "not_checked",
                     "values": values, "rawFields": raw, "issues": issues})
    return {"schemaVersion": 1, "mode": "normalized_preview_only", "customerScope": "all",
            "sheet": snapshot["sheet"], "complete": snapshot.get("complete") is True,
            "nextOffset": snapshot.get("nextOffset"), "missingFields": snapshot.get("missingFields", []),
            "databaseWritten": False, "deletionAllowed": False,
            "summary": {"records": len(rows), "rowsWithIssues": sum(bool(row["issues"]) for row in rows),
                        "customers": dict(Counter(row["values"]["customer"] or "<unresolved>" for row in rows)),
                        "issues": dict(Counter(item["code"] for row in rows for item in row["issues"]))},
            "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Output must differ from the source preview")
    try:
        result = normalize(json.loads(args.input.read_text(encoding="utf-8-sig")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(args.output)
        print(json.dumps(result["summary"], ensure_ascii=True))
    except (OSError, ValueError, PreviewError) as exc:
        parser.exit(1, f"Normalization failed: {exc}\n")


if __name__ == "__main__":
    main()
