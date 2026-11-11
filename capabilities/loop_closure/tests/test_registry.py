import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("registry", ROOT / "registry.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

SOURCE = Path(__file__).read_bytes()
REG = "capabilities/loop_closure/tests/test_registry.py::test_index_clear_keeps_red_green_not_tested"
KNOWN = {REG: SOURCE}
OLD = "a" * 64
NEW = "b" * 64
TS = "2026-11-02T09:00+08:00"
TS2 = "2026-11-02T10:00+08:00"
COLUMNS = list(r.REQUIRED_COLUMNS)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def entry(test=REG, fix="hard", closed=True, old=OLD, new=NEW, ts=TS, eid="C-1"):
    return {
        "id": eid, "closed": closed, "fix_kind": fix, "test_registration": test,
        "old_impl_sha256": old, "new_impl_sha256": new, "registered_by": "apo",
        "closed_at": ts,
    }


def index(entries):
    return encode({"schema_version": "correction-index/v1", "entries": entries})


def line(cells):
    return "| " + " | ".join(cells) + " |"


def table(headers, rows):
    sep = line("---" for _ in headers)
    return "\n".join([line(headers), sep, *[line(row) for row in rows]]) + "\n"


def valid_row(test=REG, ts=TS, eid="C-1"):
    return [eid, "true", "hard", test, OLD, NEW, "apo", ts]


def parsed(result):
    return json.loads(result[1])


def findings(result):
    return [item["finding"] for item in parsed(result).get("findings", [])]


class IndexTests(unittest.TestCase):
    def test_index_clear_keeps_red_green_not_tested(self):
        code, raw = r.assess_index(index([entry()]), KNOWN)
        body = json.loads(raw)
        self.assertEqual(code, 0)
        self.assertEqual(body["result"], "NO_REGRESSION")
        self.assertNotIn("CLOSED", body["result"])
        self.assertEqual(body["old_impl_red_green"], "NOT_TESTED")
        self.assertEqual(body["entries"], [{"id": "C-1", "closed": True, "fix_kind": "hard"}])
        self.assertIn("NOT_TESTED", body["scope"])

    def test_soft_fix_is_not_rewritten_to_hard(self):
        code, raw = r.assess_index(index([entry(fix="soft", closed=True)]), KNOWN)
        body = json.loads(raw)
        self.assertEqual(code, 0)
        self.assertEqual(body["entries"][0]["fix_kind"], "soft")
        self.assertEqual(body["old_impl_red_green"], "NOT_TESTED")

    def test_empty_and_unknown_test_names(self):
        rows = [
            entry(test="", eid="C-1", ts=TS),
            entry(test="pkg/tests/test_missing.py::test_not_in_source", eid="C-2", ts=TS2),
            entry(test="pkg/tests/test_missing.py::\u200b", eid="C-3", ts="2026-11-02T11:00+08:00"),
        ]
        code, raw = r.assess_index(index(rows), KNOWN)
        self.assertEqual(code, 1)
        got = findings((code, raw))
        self.assertEqual(got.count("empty_test_name"), 2)
        self.assertIn("missing_test_name", got)
        self.assertEqual(parsed((code, raw))["old_impl_red_green"], "NOT_TESTED")

    def test_equal_impl_shas_are_a_finding(self):
        code, raw = r.assess_index(index([entry(new=OLD)]), KNOWN)
        self.assertEqual(code, 1)
        self.assertIn("impl_sha_not_distinct", findings((code, raw)))

    def test_index_input_errors_stay_5_and_do_not_claim_red_green(self):
        cases = [
            index([entry(ts="2026-11-02T09:00:00Z")]),
            index([entry(ts=TS2), entry(eid="C-2", ts=TS)]),
            index([entry(), entry(eid="C-1", ts=TS2)]),
            encode({"schema_version": "correction-index/v1", "entries": [entry()], "status": "closed"}),
            b"",
        ]
        for raw in cases:
            code, out = r.assess_index(raw, KNOWN)
            self.assertEqual(code, 5, raw[:80])
            self.assertEqual(parsed((code, out))["result"], "INPUT_ERROR")
            self.assertEqual(parsed((code, out))["old_impl_red_green"], "NOT_TESTED")
            self.assertNotEqual(code, 1)


class TableTests(unittest.TestCase):
    def test_exact_columns_pass(self):
        code, raw = r.assess_registry_table(table(COLUMNS, [valid_row()]), KNOWN)
        body = json.loads(raw)
        self.assertEqual(code, 0)
        self.assertEqual(body["result"], "NO_REGRESSION")
        self.assertNotIn("CLOSED", body["result"])
        self.assertEqual(body["columns"], COLUMNS)

    def test_hidden_table_column(self):
        headers = list(COLUMNS)
        headers[3] = "<!-- test_registration -->"
        code, raw = r.assess_registry_table(table(headers, [valid_row()]), KNOWN)
        self.assertEqual(code, 1)
        got = findings((code, raw))
        self.assertIn("hidden_table_column", got)
        self.assertIn("registry_columns_mismatch", got)

        hidden = list(valid_row())
        hidden[3] = f'<span style="display:none">{REG}</span>'
        code, raw = r.assess_registry_table(table(COLUMNS, [hidden]), KNOWN)
        self.assertEqual(code, 1)
        self.assertIn("hidden_table_column", findings((code, raw)))
        self.assertEqual(parsed((code, raw))["result"], "REGRESSION")

    def test_missing_reordered_and_empty_test_names(self):
        short = [name for name in COLUMNS if name != "test_registration"]
        short_row = [cell for cell, name in zip(valid_row(), COLUMNS) if name != "test_registration"]
        code, raw = r.assess_registry_table(table(short, [short_row]), KNOWN)
        self.assertEqual(code, 1)
        self.assertIn("registry_columns_mismatch", findings((code, raw)))

        swapped_h = list(COLUMNS)
        swapped_h[0], swapped_h[1] = swapped_h[1], swapped_h[0]
        swapped_r = valid_row()
        swapped_r[0], swapped_r[1] = swapped_r[1], swapped_r[0]
        code, raw = r.assess_registry_table(table(swapped_h, [swapped_r]), KNOWN)
        self.assertEqual(code, 1)
        self.assertIn("registry_columns_mismatch", findings((code, raw)))

        blank = valid_row(test="   ")
        unknown = valid_row(test="pkg/tests/test_missing.py::test_not_in_source", ts=TS2, eid="C-2")
        code, raw = r.assess_registry_table(table(COLUMNS, [blank, unknown]), KNOWN)
        self.assertEqual(code, 1)
        got = findings((code, raw))
        self.assertIn("empty_test_name", got)
        self.assertIn("missing_test_name", got)
        self.assertEqual(got, sorted(got))

    def test_fullwidth_header_still_matches_column(self):
        headers = list(COLUMNS)
        headers[3] = "\uff54est_registration"
        code, raw = r.assess_registry_table(table(headers, [valid_row()]), KNOWN)
        self.assertEqual((code, parsed((code, raw))["result"]), (0, "NO_REGRESSION"))

    def test_bad_table_is_input_error_not_regression(self):
        self.assertEqual(r.assess_registry_table("", KNOWN)[0], 5)
        self.assertEqual(r.assess_registry_table(table(COLUMNS, [valid_row(ts="2026-11-02T09:00Z")]), KNOWN)[0], 5)
        code, raw = r.assess_registry_table("not a table", KNOWN)
        self.assertEqual(code, 5)
        self.assertEqual(parsed((code, raw))["result"], "INPUT_ERROR")


if __name__ == "__main__":
    unittest.main()
