import io
import json
import unittest
from unittest.mock import patch

from pull_preview import PreviewError, call_script, collect


def page(ids, cursor=None):
    return {"schemaVersion": 1, "mode": "read_only", "sheet": {"name": "OL"},
            "fields": ["库位"], "missingFields": [],
            "records": [{"id": item, "fields": {"库位": "A-01"}} for item in ids],
            "nextOffset": cursor}


class PreviewTests(unittest.TestCase):
    def test_pagination_preserves_identity_and_location(self):
        calls = []
        pages = iter([page(["a"], "next"), page(["b"])])
        def fetch(args):
            calls.append(args)
            return next(pages)
        result = collect(fetch, "OL", 2, 20)
        self.assertTrue(result["complete"])
        self.assertEqual(calls[1]["offset"], "next")
        self.assertEqual(result["records"][1], {"id": "b", "fields": {"库位": "A-01"}})

    def test_page_budget_is_not_full_snapshot(self):
        result = collect(lambda _: page(["a"], "next"), "OL", 1, 20)
        self.assertFalse(result["complete"])
        self.assertEqual(result["nextOffset"], "next")

    def test_duplicate_records_fail(self):
        pages = iter([page(["a"], "next"), page(["a"])])
        with self.assertRaisesRegex(PreviewError, "Duplicate"):
            collect(lambda _: next(pages), "OL", 2, 20)

    def test_repeated_cursor_fails(self):
        pages = iter([page(["a"], "next"), page(["b"], "next")])
        with self.assertRaisesRegex(PreviewError, "repeated"):
            collect(lambda _: next(pages), "OL", 2, 20)

    def test_schema_change_fails(self):
        changed = page(["b"])
        changed["fields"] = ["件数"]
        pages = iter([page(["a"], "next"), changed])
        with self.assertRaisesRegex(PreviewError, "fields changed"):
            collect(lambda _: next(pages), "OL", 2, 20)

    def test_wrong_sheet_fails(self):
        with self.assertRaisesRegex(PreviewError, "different sheet"):
            collect(lambda _: page([]), "DS", 1, 20)

    def test_http_result_envelope(self):
        expected = page(["a"])
        for result in (expected, json.dumps(expected)):
            with patch("pull_preview.urllib.request.build_opener") as opener:
                opener.return_value.open.return_value = io.BytesIO(json.dumps(
                    {"status": "finished", "data": {"result": result}}).encode())
                self.assertEqual(call_script("https://example.invalid", "test", {"sheet": "OL"}), expected)
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(json.loads(request.data), {"Context": {"argv": {"sheet": "OL"}}})

    def test_failed_or_unexpected_result(self):
        for envelope in ({"status": "running"}, {"status": "finished", "data": {"result": {}}}):
            with patch("pull_preview.urllib.request.build_opener") as opener:
                opener.return_value.open.return_value = io.BytesIO(json.dumps(envelope).encode())
                with self.assertRaises(PreviewError):
                    call_script("https://example.invalid", "test", {})


if __name__ == "__main__":
    unittest.main()
