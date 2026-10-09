"""Check saved TEST_ONLY browser responses; does not operate a browser or a database."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(path: Path):
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["test_only"] is True and saved["production_ready"] is False
    records = saved["records"]
    results = []

    def record(name, status=200):
        match = [r for r in records if r["name"] == name][-1]
        assert match["status"] == status, (name, match["status"])
        return match["data"]

    def passed(name):
        results.append({"name": name, "status": "PASS"})

    for domain, load_id in (("PRIVATE", 1), ("FBA", 2), ("EXPIRING", 4)):
        for suffix, status in (("empty upload", 422), ("invalid file", 415),
                               ("wrong warehouse", 422), ("oversized upload", 413),
                               ("wrong business", 422), ("viewer upload", 403),
                               ("viewer dispatch", 403), ("viewer approval", 403)):
            response = record(f"{domain} {suffix}", status)
            assert "detail" in response
            passed(f"{domain} {suffix}: server rejected {status}")
        uploaded = record(f"{domain} upload")
        corrected = record(f"{domain} corrected upload")
        assert uploaded["load_id"] == corrected["load_id"] == load_id
        assert uploaded["dispatch_business_type"] == corrected["dispatch_business_type"]
        assert uploaded["id"] != corrected["id"]
        assert corrected["version"] > uploaded["version"]
        passed(f"{domain} correction appends a document version")
        repeated = record(f"{domain} repeat review")
        accepted = [r["data"] for r in records if r["name"] == "DOCUMENTS ACCEPT"
                    and r["data"]["load_id"] == load_id][0]
        assert repeated["id"] == accepted["id"]
        passed(f"{domain} repeated review reuses the persisted review")
        rejected = record(f"{domain} rejected state")
        checks = {c["kind"]: c for c in rejected["checks"]}
        assert checks["DOCUMENTS"]["status"] == "BLOCKED"
        assert checks["DOCUMENTS"]["reason"] == "REVIEW_REJECTED"
        assert checks["APPROVAL"]["status"] == "BLOCKED"
        old_approval_id = checks["APPROVAL"]["review"]["id"]
        rejection_id = checks["DOCUMENTS"]["review"]["id"]
        final = record(f"{domain} final history")
        current = {c["kind"]: c for c in final["checks"]}
        assert current["APPROVAL"]["review"]["id"] != old_approval_id
        assert any(h["id"] == rejection_id and h["decision"] == "REJECT" for h in final["history"])
        assert any(h["id"] == old_approval_id for h in final["history"])
        refreshed = record(f"refresh history {load_id}")
        assert refreshed["history"] == final["history"]
        passed(f"{domain} rejection retained, old approval invalidated, history survives refresh")
        expected = "READY" if domain == "EXPIRING" else "DISPATCHED"
        load = record(f"{domain} final load")
        assert load["status"] == record(f"refresh load {load_id}")["status"] == expected
        assert all(o["status"] == ("CONFIRMED" if domain == "EXPIRING" else "DISPATCHED")
                   for o in load["outbounds"])
        passed(f"{domain} load and downstream state survive refresh")
        if domain != "EXPIRING":
            dispatched = record(f"{domain} dispatch")
            repeated_dispatch = record(f"{domain} repeated dispatch")
            assert dispatched["id"] == repeated_dispatch["id"] == load_id
            assert repeated_dispatch["status"] == "DISPATCHED"
            assert all(c["status"] == "PASS" for c in final["checks"])
            passed(f"{domain} TEST_ONLY dispatch and idempotent repeat")

    expired = record("EXPIRING expired dispatch", 409)["detail"]
    assert expired["ready"] is False
    assert any(c["reason_code"] == "EVIDENCE_EXPIRED" for c in expired["checks"])
    passed("Expired evidence: server 409 and no dispatch state write")
    unconfigured = record("unconfigured evidence")
    assert unconfigured["configured"] is False and unconfigured["policy"] is None
    assert all(c["status"] == "UNKNOWN" and c["can_review"] is False for c in unconfigured["checks"])
    blocked = record("unconfigured dispatch", 409)["detail"]
    assert blocked["ready"] is False
    assert any(c["reason_code"] == "DOCUMENT_RULES_NOT_CONFIGURED" for c in blocked["checks"])
    assert record("unconfigured refresh")["status"] == "READY"
    passed("Unconfigured policy: UNKNOWN, review disabled, server 409, state retained")
    return {"status": "PASS_TEST_ONLY_RESPONSE_ASSERTIONS", "production_ready": False,
            "source": path.name, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "record_count": len(records), "results": results,
            "limitations": ["Native file picker and the complete production page workflow remain unverified.",
                            "Upload helper success status is normalized; HTTP upload codes are in backend server logs.",
                            "These assertions check saved real-browser responses, not a new browser run."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.source)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"PASS {len(result['results'])} saved-browser assertions; TEST_ONLY, production_ready=false")
