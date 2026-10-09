"""Read-only/offline delivery audit; never opens project .env or a database.

Run with backend/.venv/Scripts/python.exe from any working directory.
Outputs contain paths/hashes and redacted finding metadata, never matched values.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FROZEN = ROOT / "docs/evidence/dispatch-candidate-final-20261007-1548"
CHECKS: list[dict] = []
REPLACEMENTS = {
    "backend/alembic.ini": "docs/evidence/dispatch-delivery-audit-20261007/sanitized-config/alembic.ini",
    "backend/.env.example": "docs/evidence/dispatch-delivery-audit-20261007/sanitized-config/.env.example",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args: list[str]):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", shell=False,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def git(*args):
    result = run(["git", *args])
    if result.returncode:
        raise RuntimeError("git read failed (output withheld)")
    return result.stdout.strip()


def check(name, condition, **details):
    CHECKS.append({"name": name, "status": "PASS" if condition else "FAIL", **details})


def source_state():
    paths = git("ls-files", "--cached", "--others", "--exclude-standard",
                "backend", "frontend", "scripts").splitlines()
    excluded = {"node_modules", ".venv", "dist", "__pycache__", ".pytest_cache"}
    return {p: sha(ROOT / p) for p in sorted(set(paths))
            if not excluded.intersection(Path(p).parts)
            and Path(p).suffix not in {".pyc", ".tsbuildinfo"}
            and (ROOT / p).is_file()}


def aggregate(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def main():
    head = git("rev-parse", "HEAD")
    index = ROOT / git("rev-parse", "--git-path", "index")
    index_before = sha(index)
    frozen = read_json(FROZEN / "candidate.json")
    files = source_state()
    changed = sorted(p for p in set(files) | set(frozen["source_files"])
                     if files.get(p) != frozen["source_files"].get(p))
    check("frozen_source", head == frozen["head"] and not changed
          and aggregate(files) == frozen["source_sha256"],
          head=head, source_files=len(files), source_sha256=aggregate(files), changed_paths=changed)
    verification = read_json(FROZEN / "verification.json")
    final_audit = read_json(FROZEN / "final-audit.json")
    results = read_json(FROZEN / "results.json")
    check("candidate_evidence_binding", verification["candidate"]["head"] == head
          and verification["candidate"]["source_sha256"] == aggregate(files)
          and final_audit["source_sha256"] == aggregate(files)
          and not results["production_ready"] and not results["mechanism_acceptance_complete"])
    checks = verification["final_checks"]
    check("recorded_checks_and_logs", len(checks) == 8
          and all(c["status"] == "PASS" and c["exit_code"] == 0
                  and (FROZEN / c["log"]).is_file() for c in checks),
          verification="REUSED_FROZEN_RESULTS_NOT_RERUN", recorded_check_count=len(checks))
    junit = ET.parse(FROZEN / "final-backend-junit.xml")
    cases = list(junit.iter("testcase"))
    skipped = [c for c in cases if c.find("skipped") is not None]
    bad = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
    check("backend_junit", len(cases) == 422 and len(skipped) == 1 and not bad
          and skipped[0].get("name") == "test_concurrent_partial_cannot_overdraw",
          passed=len(cases)-len(skipped)-len(bad), skipped=len(skipped), failed=len(bad))
    pg_log = (FROZEN / "final-postgres.log").read_text(encoding="utf-8", errors="replace")
    pg_tool = (ROOT / "scripts/verify_dispatch_isolated.py").read_text(encoding="utf-8")
    check("sqlite_skip_postgresql_mapping", "partial_cases.test_concurrent_partial_cannot_overdraw" in pg_tool
          and re.search(r"PASS.*partial completion concurrent quantities and duplicate rollback", pg_log) is not None,
          test="tests.test_migration_safety::test_concurrent_partial_cannot_overdraw",
          evidence="final-postgres.log", meaning="Same test executed on PostgreSQL; SQLite skip remains a skip")
    browser = read_json(FROZEN / "browser/results.json")
    playwright = read_json(FROZEN / "browser/playwright-results.json")
    stats = playwright["stats"]
    pngs = list((FROZEN / "browser").glob("*.png"))
    check("formal_page_evidence", len(browser["steps"]) == 16
          and all(s["status"] == "PASS" for s in browser["steps"])
          and stats["expected"] == 3 and stats["unexpected"] == 0
          and stats["skipped"] == 0 and stats["flaky"] == 0 and len(pngs) == 29,
          reused_tests=3, reused_steps=16, screenshots=len(pngs), native_file_picker="NOT_VERIFIED",
          har_trace_files=[p.relative_to(FROZEN).as_posix() for p in FROZEN.rglob("*")
                           if p.suffix in {".har", ".zip"}])
    package = read_json(ROOT / "frontend/package.json")
    lock = read_json(ROOT / "frontend/package-lock.json")["packages"][""]
    check("dependency_lock_and_windows_entry", all(package.get(k, {}) == lock.get(k, {})
          for k in ("dependencies", "devDependencies"))
          and package["scripts"]["test:e2e:dispatch"] == "node ../scripts/run_dispatch_ui.mjs"
          and (ROOT / "backend/requirements.txt").is_file())
    ts = read_json(ROOT / "frontend/tsconfig.json")
    check("strict_check_enabled", ts["compilerOptions"]["strict"] is True,
          runtime_typecheck="REUSED_FROZEN_ZERO_ERRORS_NOT_RERUN")
    node = run(["node", "--check", str(ROOT / "scripts/run_dispatch_ui.mjs")])
    check("windows_entry_syntax_offline", node.returncode == 0)
    migration = run([sys.executable, "-c",
                    "from alembic.config import Config; from alembic.script import ScriptDirectory; "
                    "c=Config(); c.set_main_option('script_location','backend/alembic'); "
                    "s=ScriptDirectory.from_config(c); print(','.join(s.get_heads())); "
                    "assert s.get_revision('20261005_0039').down_revision=='20261005_0038'; "
                    "assert s.get_revision('20261005_0038').down_revision=='20260925_0037'"])
    check("migration_graph_offline", migration.returncode == 0
          and migration.stdout.strip() == "20261005_0039", head="20261005_0039",
          database_access=False, env_py_loaded=False)
    for business in ("FBA", "PRIVATE"):
        template = ROOT / f"docs/dispatch-policy/{business}.template.json"
        draft = read_json(template)
        validation = run([sys.executable, "scripts/dispatch_policy.py", "validate", "--file", str(template)])
        check(f"{business}_unconfirmed_template_blocks_offline", validation.returncode == 2
              and draft["provenance"]["purpose"] == "PRODUCTION"
              and draft["provenance"]["confirmation_reference"] is None
              and all(v is None for v in draft["provenance"]["rule_sources"].values()),
              exit_code=validation.returncode, database_access=False, production_rule_enabled=False)

    inventory = dict(files)
    # Reviewed delivery docs and all frozen evidence; no local .env/temporary files read.
    for pattern in ("docs/*.md", "docs/dispatch-policy/*.json"):
        for path in ROOT.glob(pattern):
            inventory[path.relative_to(ROOT).as_posix()] = sha(path)
    evidence_roots = [FROZEN, HERE]
    for directory in evidence_roots:
        for path in directory.rglob("*"):
            if path.is_file() and not ({"__pycache__"}.intersection(path.parts)):
                if directory == HERE and path.name not in {"audit.py", "README.md"} and path.parent.name != "sanitized-config":
                    continue  # exclude self-referential generated reports
                inventory[path.relative_to(ROOT).as_posix()] = sha(path)
    historical = ["docs/evidence/dispatch-release-20261007/release-rehearsal.json",
                  "docs/evidence/dispatch-release-20261007/results.json",
                  "docs/evidence/dispatch-release-20261007/cleanup.json"]
    for relative in historical:
        path = ROOT / relative
        if path.is_file():
            inventory[relative] = sha(path)
    patterns = {
        "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "jwt_literal": re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
        "database_url_with_userinfo": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s'\"/@]+:[^\s'\"/@]+@"),
        "literal_secret_assignment": re.compile(r"(?i)\b(?:password|secret_key|api_key|access_token)\s*[=:]\s*['\"][^'\"\r\n]{4,}['\"]"),
        "env_secret_assignment": re.compile(r"(?im)^JWT_SECRET_KEY\s*=\s*\S+"),
    }
    findings = []
    for relative in sorted(inventory):
        path = ROOT / relative
        if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".md", ".ini", ".yml", ".yaml", ".log", ".xml", ".txt", ".example"}:
            continue
        contents = path.read_text(encoding="utf-8", errors="replace")
        for category, pattern in patterns.items():
            for match in pattern.finditer(contents):
                context = "ISOLATED_TEST_OR_EVIDENCE" if ("/tests/" in relative or "/e2e/" in relative or relative.startswith("scripts/") or relative.startswith("docs/evidence/")) else "REVIEW_REQUIRED"
                if relative in REPLACEMENTS:
                    context = "RESTRICTED_ORIGINAL_NOT_EXPORTABLE_VALUE_VALIDITY_UNKNOWN"
                elif relative in REPLACEMENTS.values():
                    context = "REVIEWED_REDACTED_PLACEHOLDER_TEMPLATE"
                elif relative == "backend/scripts/phase11_1_postgres_smoke.py":
                    context = "REVIEWED_LEGACY_TEST_FIXTURE_NOT_APPROVED_ISOLATION_ENTRY"
                elif relative in {"backend/config/dev.env.example", "backend/config/test.env.example"}:
                    if "Synthetic " in contents and "Never copy production secrets." in contents:
                        context = "REVIEWED_SYNTHETIC_ENVIRONMENT_TEMPLATE_NOT_PRODUCTION_CONFIGURATION"
                elif "/tests/" in relative or relative.endswith("junit.xml"):
                    context = "REVIEWED_SYNTHETIC_TEST_FIXTURE_OR_CAPTURED_TEST_EXAMPLE"
                findings.append({"path": relative, "line": contents.count("\n", 0, match.start())+1,
                                 "category": category, "context": context})
    replacement_valid = True
    restricted = []
    for original, replacement in REPLACEMENTS.items():
        contents = (ROOT / original).read_text(encoding="utf-8-sig")
        sanitized, count = re.subn(r"postgres(?:ql)?(?:\+\w+)?://[^\s\r\n]+",
                                  "postgresql+psycopg://<USERNAME>:<PASSWORD>@<HOST>:<PORT>/<DATABASE>", contents)
        replacement_valid &= count == 1
        if original.endswith(".env.example"):
            sanitized, count = re.subn(r"(?m)^(JWT_SECRET_KEY\s*=).*$", r"\1<REQUIRED_SECRET>", sanitized)
            replacement_valid &= count == 1
        replacement_valid &= (ROOT / replacement).read_text(encoding="utf-8") == sanitized
        tracked = run(["git", "show", f"HEAD:{original}"])
        restricted.append({"path": original, "sha256": files[original], "replacement": replacement,
                           "reason": "Credential-bearing URL; validity unknown; do not export original",
                           "unchanged_from_HEAD": tracked.returncode == 0 and tracked.stdout == contents})
        inventory.pop(original)
    check("sanitized_replacement_contract", replacement_valid,
          originals_preserved=True, active_configuration_changed=False, replacements_require_secure_provisioning=True)
    unreviewed_findings = sum(f["context"] == "REVIEW_REQUIRED" for f in findings)
    check("credential_filename_exclusion", not any(Path(p).name.startswith(".env")
          and Path(p).name != ".env.example" for p in inventory) and unreviewed_findings == 0,
          scope="Selected deliverable text only; excluded .env and local resources were never read",
          content_findings=len(findings), findings_require_context_review=True,
          unreviewed_content_findings=unreviewed_findings)
    check("git_index_unchanged", sha(index) == index_before)
    check("source_unchanged_during_audit", source_state() == files and git("rev-parse", "HEAD") == head)
    status_lines = git("status", "--short", "--untracked-files=all").splitlines()
    excluded_paths = [line[3:] for line in status_lines if line[3:] not in inventory]
    manifest = {"format": "sha256-by-relative-path", "source_sha256": aggregate(files),
                "source_files": files, "delivery_files": dict(sorted(inventory.items())),
                "restricted_originals": restricted,
                "delivery_replacements": REPLACEMENTS,
                "self_generated_outputs_excluded": ["results.json", "manifest.json", "workspace-summary.json"],
                "local_workspace_not_selected": excluded_paths, "no_files_deleted_staged_or_committed": True}
    report = {"audited_at": datetime.now(timezone.utc).isoformat(),
              "status": "PASS" if all(c["status"] == "PASS" for c in CHECKS) else "FAIL",
              "checks": CHECKS, "candidate": {"head": head, "source_sha256": aggregate(files)},
              "credential_scan_findings_redacted": findings,
              "credential_delivery_gate": "ORIGINAL_CONFIGS_HELD_BACK_SECURE_PROVISIONING_NOT_PERFORMED",
              "prior_test_results": "REUSED_FROZEN_EVIDENCE_NOT_CURRENT_TEST_RUNS",
              "runtime_code_changed": False, "services_started": [], "cleanup": "NOT_APPLICABLE_NO_RESOURCES_CREATED",
              "production_operations": False, "native_file_picker": "NOT_VERIFIED",
              "mechanism_acceptance_complete": False, "production_ready": False}
    for name, value in (("manifest.json", manifest), ("results.json", report),
                        ("workspace-summary.json", {"head": head, "status_lines": status_lines,
                         "diff_stat": git("diff", "--stat"), "staged_diff_stat": git("diff", "--cached", "--stat")})):
        (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "source_files": len(files), "delivery_files": len(inventory),
                      "checks": [{"name": c["name"], "status": c["status"]} for c in CHECKS],
                      "redacted_content_findings": len(findings)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
