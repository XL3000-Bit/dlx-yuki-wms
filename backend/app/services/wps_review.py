"""Read-only reconciliation of normalized WPS snapshots; never stages inventory."""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation


def quantity(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def reconcile(sheets):
    groups = defaultdict(lambda: {"OL": [], "提柜": []})
    for sheet in sheets:
        for row in sheet["rows"]:
            container = row["values"].get("container_number")
            if container:
                groups[str(container).strip().upper()][sheet["sheet"]].append(row)
    complete = len(sheets) == 2 and all(s["complete"] for s in sheets)
    result = []
    for container, group in sorted(groups.items()):
        ol, inbound = group["OL"], group["提柜"]
        counts = [quantity(r["values"].get("carton_qty")) for r in ol]
        actual = sum(counts, Decimal(0)) if counts and None not in counts else None
        expected = quantity(inbound[0]["values"].get("carton_qty")) if len(inbound) == 1 else None
        difference = actual - expected if actual is not None and expected is not None else None
        if not ol or not inbound:
            status = "missing_counterpart"
        elif len(inbound) != 1:
            status = "ambiguous_inbound"
        elif difference is None:
            status = "missing_quantity"
        elif not complete:
            status = "partial_snapshot"
        else:
            status = "matched" if difference == 0 else "difference"
        result.append({"container": container, "olRows": len(ol), "inboundRows": len(inbound),
                       "olCartons": str(actual) if actual is not None else None,
                       "inboundCartons": str(expected) if expected is not None else None,
                       "difference": str(difference) if difference is not None else None, "status": status})
    return result


def review(sheets, customers, locations, warehouse_id=None, overrides=None):
    sheets = deepcopy(sheets)
    overrides = overrides or {}
    by_id = {c.id: c for c in customers if c.is_active}
    location_codes = {loc.location_code.strip().upper() for loc in locations
                      if loc.is_active and loc.warehouse_id == warehouse_id}
    for sheet in sheets:
        for row in sheet["rows"]:
            identity = row["sourceIdentity"]
            row["key"] = ":".join(str(identity[k]) for k in ("documentId", "sheetId", "recordId"))
            raw_customer = row["values"].get("customer")
            name = str(raw_customer or "").strip().casefold()
            matches = [c.id for c in by_id.values() if name and name in
                       {c.customer_code.strip().casefold(), c.customer_name.strip().casefold()}]
            override = overrides.get(row["key"])
            if override is not None:
                if override not in by_id:
                    raise ValueError("客户映射包含无效或停用客户")
                row["customerId"], row["customerMatchStatus"] = override, "manual"
            else:
                row["customerId"] = matches[0] if len(matches) == 1 else None
                row["customerMatchStatus"] = "matched" if len(matches) == 1 else "ambiguous" if matches else "unmatched"
            candidates = row["values"].get("location_candidates", [])
            row["unknownLocations"] = [code for code in candidates if code not in location_codes] if warehouse_id else []
            row["locationStatus"] = ("not_applicable" if sheet["sheet"] != "OL" else
                "warehouse_required" if warehouse_id is None else "missing" if not candidates else
                "needs_review" if row["unknownLocations"] or any(i["code"] == "pallet_suffix_needs_review" for i in row["issues"]) else "matched")
    return {"mode": "review_only", "databaseWritten": False, "customerScope": "all", "warehouseId": warehouse_id,
            "sheets": sheets, "reconciliation": reconcile(sheets)}
