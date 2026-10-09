"""Read-only candidate discovery, not an inventory balance or import decision."""
from collections import Counter, defaultdict


def identity_key(identity):
    if not isinstance(identity, dict):
        return None
    parts = [identity.get(k) for k in ("documentId", "sheetId", "recordId")]
    if any(not isinstance(p, (str, int)) or isinstance(p, bool) or not str(p).strip() for p in parts):
        return None
    return tuple(str(p) for p in parts)


def annotate_duplicates(sheets, records):
    by_source, by_container = defaultdict(list), defaultdict(list)
    for record in records:
        metadata = record.source_metadata or {}
        key = identity_key(metadata.get("sourceIdentity")) if isinstance(metadata, dict) else None
        if key:
            by_source[key].append(record)
        container = (record.container_number or "").strip().upper()
        if container:
            by_container[container].append(record)
    source_counts = Counter(identity_key(r.get("sourceIdentity")) for s in sheets for r in s["rows"])
    summary = Counter()
    for sheet in sheets:
        for row in sheet["rows"]:
            key = identity_key(row.get("sourceIdentity"))
            container = str(row["values"].get("container_number") or "").strip().upper()
            exact = by_source.get(key, []) if key else []
            candidates = exact or by_container.get(container, [])
            if sheet["sheet"] != "OL":
                status, candidates = "not_applicable", []
            elif key is None:
                status = "invalid_source"
            elif source_counts[key] > 1:
                status = "duplicate_source"
            elif len(exact) > 1:
                status = "source_conflict"
            elif exact:
                status = "source_linked"
            elif not container:
                status = "missing_container"
            elif candidates:
                status = "history_candidate"
            else:
                status = "no_candidate"
            # Include all warehouses/customers: mismatches must not hide a possible duplicate.
            row["duplicateCheck"] = {"status": status, "candidateCount": len(candidates), "candidates": [
                {"id": r.id, "inboundNo": r.inbound_no, "container": r.container_number,
                 "customerId": r.customer_id, "warehouseId": r.warehouse_id, "destination": r.fc_code,
                 "cartons": str(r.carton_qty), "pallets": str(r.pallet_qty),
                 "location": r.raw_location_text, "status": r.status}
                for r in sorted(candidates, key=lambda r: r.id)[:10]
            ]}
            if sheet["sheet"] == "OL":
                summary[status] += 1
    return {"scope": "all_inbound_records", "recordsChecked": len(records), "counts": dict(summary),
            "importAllowed": False, "inventoryBalanceChecked": False}
