#!/usr/bin/env python3
"""Direct v1/v2 read-only shadow comparison. Stores metadata, never tokens/bodies."""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

V1 = os.getenv("SHADOW_V1_BASE", "http://127.0.0.1:8000").rstrip("/")
V2 = os.getenv("SHADOW_V2_BASE", "http://127.0.0.1:8081").rstrip("/")
OUT = Path(os.getenv("SHADOW_OUTPUT_DIR", "build/shadow-read"))


def request(base, path, token=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, headers=headers), timeout=10) as res:
            raw, status = res.read(), res.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    except Exception as exc:
        return {"status": None, "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": type(exc).__name__}
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    try:
        value = json.loads(raw)
    except Exception:
        return {"status": status, "latency_ms": elapsed, "json": False,
                "body_sha256": hashlib.sha256(raw).hexdigest()}
    result = {"status": status, "latency_ms": elapsed, "json": True,
              "shape": shape(value), "count": len(value) if isinstance(value, list) else None}
    if status >= 400 and isinstance(value, dict):
        result["detail"] = value.get("detail")
    if status == 200:
        result["canonical_sha256"] = digest(value)
    return result


def shape(value):
    if isinstance(value, dict):
        return {key: shape(val) for key, val in sorted(value.items())}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    if value is None:
        return "null"
    return type(value).__name__


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def pair(name, v1_path, v2_path, token, classification="COMPARABLE"):
    if token is None:
        return {"name": name, "classification": "NOT_EXECUTED_NO_SAFE_CREDENTIAL"}
    left, right = request(V1, v1_path, token), request(V2, v2_path, token)
    result = {"name": name, "classification": classification, "v1": left, "v2": right}
    if classification == "COMPARABLE":
        result["status_match"] = left.get("status") == right.get("status")
        result["count_match"] = left.get("count") == right.get("count")
        result["shape_match"] = left.get("shape") == right.get("shape")
    return result


def main():
    admin = os.getenv("SHADOW_ADMIN_TOKEN")
    scoped = os.getenv("SHADOW_SCOPED_TOKEN")
    malformed = "not-a-valid-jwt"
    cases = [
        {"name": "v1_health", "classification": "CONTRACT_DIFFERENCE", "result": request(V1, "/health")},
        {"name": "v2_health", "classification": "CONTRACT_DIFFERENCE", "result": request(V2, "/api/v2/health")},
        {"name": "v2_db_health", "classification": "NO_EQUIVALENT_V1", "result": request(V2, "/api/v2/health/db")},
        {"name": "customers_no_token", "v1": request(V1, "/api/v1/master-data/customers"),
         "v2": request(V2, "/api/v2/customers")},
        {"name": "customers_malformed_token", "v1": request(V1, "/api/v1/master-data/customers", malformed),
         "v2": request(V2, "/api/v2/customers", malformed)},
    ]
    for label, token in (("admin", admin), ("scoped", scoped)):
        for name, one, two in (
            ("customers", "/api/v1/master-data/customers", "/api/v2/customers"),
            ("warehouses", "/api/v1/master-data/warehouses", "/api/v2/warehouses"),
            ("carriers", "/api/v1/master-data/carriers", "/api/v2/carriers"),
            ("fc_addresses", "/api/v1/master-data/amazon-fc-addresses", "/api/v2/fc-addresses"),
        ):
            cases.append(pair(label + "_" + name, one, two, token))
        cases.append(pair(label + "_dashboard", "/api/v1/dashboard/operations",
                          "/api/v2/reporting/dashboard", token, "CONTRACT_DIFFERENCE"))
    reachable = cases[0]["result"].get("status") is not None and cases[1]["result"].get("status") is not None
    blockers = []
    if not reachable:
        blockers.append("SERVICES_NOT_REACHABLE")
    if not admin or not scoped:
        blockers.append("SAFE_ADMIN_AND_SCOPED_TOKENS_NOT_SUPPLIED")
    if os.getenv("SHADOW_SAME_DATASOURCE_VERIFIED") != "true":
        blockers.append("SAME_DATASOURCE_NOT_VERIFIED")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "v1_base": V1, "v2_base": V2,
        "result": "BLOCKED" if blockers else "PARTIAL",
        "blockers": blockers, "cases": cases,
        "secrets_persisted": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "shadow-read-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"result": summary["result"], "blockers": blockers, "case_count": len(cases)}))


if __name__ == "__main__":
    main()
