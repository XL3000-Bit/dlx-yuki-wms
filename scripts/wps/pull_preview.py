"""Read WPS AirScript into a local preview. No YUKI database writes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SHEETS = ("提柜", "OL", "DS", "出库")


class PreviewError(Exception):
    pass


def config(path: Path) -> tuple[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    url = os.environ.get("WPS_AIRSCRIPT_WEBHOOK", values.get("WPS_AIRSCRIPT_WEBHOOK", ""))
    token = os.environ.get("WPS_AIRSCRIPT_TOKEN", values.get("WPS_AIRSCRIPT_TOKEN", ""))
    if not re.fullmatch(r"https://www\.kdocs\.cn/api/v3/ide/file/[A-Za-z0-9_-]+/script/[A-Za-z0-9_-]+/sync_task", url):
        raise PreviewError("Missing/invalid WPS_AIRSCRIPT_WEBHOOK in .env.wps")
    if not token or "\n" in token or "\r" in token:
        raise PreviewError("Missing/invalid WPS_AIRSCRIPT_TOKEN in .env.wps")
    return url, token


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the personal token to another endpoint.
        return None


def call_script(url: str, token: str, argv: dict) -> dict:
    request = urllib.request.Request(url,
        data=json.dumps({"Context": {"argv": argv}}).encode(),
        headers={"Content-Type": "application/json", "AirScript-Token": token}, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise PreviewError("WPS response exceeds preview size limit")
        envelope = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise PreviewError(f"WPS HTTP {exc.code}; check token and script permissions") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise PreviewError("WPS connection failed or returned invalid JSON") from None
    if not isinstance(envelope, dict) or envelope.get("status") != "finished" or envelope.get("error"):
        raise PreviewError("WPS script did not finish successfully; inspect WPS execution log")
    data = envelope.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            raise PreviewError("Unexpected script result") from None
    if not isinstance(result, dict) or result.get("schemaVersion") != 1 or result.get("mode") != "read_only":
        raise PreviewError("Install scripts/wps/airscript_readonly.js before pulling")
    return result


def collect(fetch, sheet: str, max_pages: int, page_size: int) -> dict:
    records, seen_ids, seen_offsets = [], set(), set()
    offset = ""
    fields = missing = None
    sheet_id = None
    for _ in range(max_pages):
        page = fetch({"sheet": sheet, "pageSize": page_size, "offset": offset})
        if not isinstance(page.get("sheet"), dict) or page["sheet"].get("name") != sheet:
            raise PreviewError("WPS returned a different sheet")
        current_id = page["sheet"].get("id")
        if fields is not None and current_id != sheet_id:
            raise PreviewError("Sheet identity changed during read; retry")
        sheet_id = current_id
        if not isinstance(page.get("records"), list) or not isinstance(page.get("fields"), list):
            raise PreviewError("Invalid page format")
        if fields is not None and fields != page["fields"]:
            raise PreviewError("Sheet fields changed during read; retry")
        fields, missing = page["fields"], page.get("missingFields", [])
        for record in page["records"]:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"] or not isinstance(record.get("fields"), dict):
                raise PreviewError("Invalid WPS record identity/fields")
            if record["id"] in seen_ids:
                raise PreviewError("Duplicate record across pages; source may have changed, retry")
            seen_ids.add(record["id"])
            records.append(record)
        offset = page.get("nextOffset")
        if offset is not None and not isinstance(offset, str):
            raise PreviewError("Invalid pagination cursor")
        if not offset:
            break
        if offset in seen_offsets:
            raise PreviewError("WPS repeated pagination cursor")
        seen_offsets.add(offset)
    return {"source":"wps_airscript", "mode":"preview_only", "sheet":sheet, "sheetId":sheet_id,
            "fields":fields, "missingFields":missing, "records":records,
            "complete":not bool(offset), "nextOffset":offset or None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", choices=SHEETS, default="提柜")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.wps")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/wps/preview.json")
    args = parser.parse_args()
    if not 1 <= args.max_pages <= 1000 or not 1 <= args.page_size <= 100:
        parser.error("max-pages must be 1..1000; page-size must be 1..100")
    try:
        url, token = config(args.env_file)
        result = collect(lambda argv: call_script(url, token, argv), args.sheet, args.max_pages, args.page_size)
        result["documentId"] = url.split("/file/", 1)[1].split("/", 1)[0]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(args.output)
        print(json.dumps({"sheet": args.sheet, "records":len(result["records"]),
                          "complete":result["complete"], "missingFields":result["missingFields"],
                          "output":str(args.output)}, ensure_ascii=False))
        return 0
    except (PreviewError, OSError) as exc:
        print(f"Preview failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
