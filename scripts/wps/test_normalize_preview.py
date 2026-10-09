import unittest
from normalize_preview import normalize
from pull_preview import PreviewError, collect


def sample(fields):
    return {"source": "wps_airscript", "mode": "preview_only", "sheet": "OL",
            "documentId": "doc", "sheetId": 1, "complete": False, "nextOffset": "next",
            "fields": list(fields), "records": [{"id": "r1", "fields": fields}]}


class NormalizeTests(unittest.TestCase):
    def test_preserves_arrays_raw_location_and_null_zero(self):
        raw = {"客户": ["Customer A"], "柜号": "TEST123", "拆柜时间": ["2026/09/01"],
               "库位": "C14 \nE15", "FBA": ["F1", "F2"], "PO": ["P1", "P2"],
               "板数": None, "件数": 0}
        result = normalize(sample(raw))
        row = result["rows"][0]
        self.assertEqual(row["rawFields"], raw)
        self.assertEqual(row["values"]["customer"], "Customer A")
        self.assertEqual(row["values"]["unload_date"], "2026-09-01")
        self.assertEqual(row["values"]["location_candidates"], ["C14", "E15"])
        self.assertEqual(row["values"]["fba_references"], ["F1", "F2"])
        self.assertIsNone(row["values"]["pallet_qty"])
        self.assertEqual(row["values"]["carton_qty"], "0")
        self.assertFalse(result["complete"])
        self.assertFalse(result["deletionAllowed"])

    def test_all_customers_including_missing_are_retained(self):
        source = sample({"客户": "A"})
        source["records"] += [{"id": "r2", "fields": {"客户": ["B"]}}, {"id": "r3", "fields": {}}]
        self.assertEqual(normalize(source)["summary"]["customers"], {"A": 1, "B": 1, "<unresolved>": 1})

    def test_ambiguous_customer_location_and_nonfinite_numbers_flagged(self):
        row = normalize(sample({"客户": ["A", "B"], "库位": "D21-8P,D23-1P", "件数": "NaN"}))["rows"][0]
        self.assertIsNone(row["values"]["customer"])
        self.assertIsNone(row["values"]["carton_qty"])
        self.assertTrue({"multiple_values", "pallet_suffix_needs_review", "invalid_number"}.issubset(
            {item["code"] for item in row["issues"]}))

    def test_identity_stable_when_manual_location_changes(self):
        first = normalize(sample({"库位": "A1"}))["rows"][0]
        second = normalize(sample({"库位": "B1"}))["rows"][0]
        self.assertEqual(first["sourceIdentity"], second["sourceIdentity"])
        self.assertEqual(first["customerMatchStatus"], "not_checked")

    def test_duplicate_identity_rejected_but_duplicate_container_retained(self):
        source = sample({"柜号": "TEST"})
        source["records"].append({"id": "r2", "fields": {"柜号": "TEST"}})
        self.assertEqual(normalize(source)["summary"]["records"], 2)
        source["records"][1]["id"] = "r1"
        with self.assertRaises(PreviewError):
            normalize(source)

    def test_sheet_identity_change_rejected(self):
        pages = iter([{"sheet": {"name": "OL", "id": i}, "fields": [], "records": [],
                       "nextOffset": "next" if i == 1 else None} for i in (1, 2)])
        with self.assertRaisesRegex(PreviewError, "identity changed"):
            collect(lambda _: next(pages), "OL", 2, 20)

    def test_inbound_and_unsupported_sheet(self):
        source = sample({"客户": "A", "ETA": ["2026/09/01"], "船司": "Carrier"})
        source["sheet"] = "提柜"
        row = normalize(source)["rows"][0]
        self.assertEqual(row["values"]["eta"], "2026-09-01")
        self.assertEqual(row["values"]["carrier"], "Carrier")
        source["sheet"] = "DS"
        with self.assertRaises(PreviewError):
            normalize(source)
