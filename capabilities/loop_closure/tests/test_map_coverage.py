import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("map_coverage", ROOT / "map_coverage.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

ALIASES = {"生产方": ["producer", "Producer"], "验收方": ["reviewer"]}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def step(sid="s1", source="stdout sha256 " + "ab" * 32):
    return {"id": sid, "command": ["python3", "-m", "unittest"],
            "expected": "exit 0", "measured_source": source}


def document(steps=None, author="生产方", verifier="验收方"):
    return {"schema_version": "loop-map/v1", "author": author, "verifier": verifier,
            "steps": [step()] if steps is None else list(steps)}


def receipt_for(map_bytes, ids=("s1",)):
    return {"schema_version": "loop-map-receipt/v1",
            "map_sha256": hashlib.sha256(map_bytes).hexdigest(),
            "steps": [{"id": sid} for sid in ids]}


def run(doc=None, ids=None, expected=None, aliases=ALIASES, receipt=None):
    raw = encode(document() if doc is None else doc)
    rec = encode(receipt_for(raw, ids if ids is not None else tuple(
        step["id"] for step in (document() if doc is None else doc)["steps"]
    )) if receipt is None else receipt)
    pin = hashlib.sha256(raw).hexdigest() if expected is None else expected
    return m.assess_map(raw, rec, pin, aliases)


def body(result):
    return json.loads(result[1])


def names(result):
    return [item["finding"] for item in body(result).get("findings", [])]


class MapCoverageTests(unittest.TestCase):
    def test_matching_map_is_no_regression_and_not_closed(self):
        code, raw = run()
        parsed = json.loads(raw)
        self.assertEqual(code, 0)
        self.assertEqual(parsed["result"], "NO_REGRESSION")
        self.assertNotIn("CLOSED", parsed["result"])
        self.assertIn("not loop closure", parsed["scope"])
        self.assertEqual(parsed["findings"], [])

    def test_empty_steps_rejected(self):
        code, raw = run(document([]), ids=())
        self.assertEqual(code, 1)
        self.assertIn("empty_steps", names((code, raw)))
        self.assertEqual(body((code, raw))["result"], "REGRESSION")

    def test_missing_and_extra_coverage(self):
        doc = document([step("s1"), step("s2")])
        code, raw = run(doc, ids=("s1", "s3"))
        self.assertEqual(code, 1)
        self.assertEqual(names((code, raw)), ["coverage_extra", "coverage_missing"])
        details = {item["finding"]: item["detail"] for item in body((code, raw))["findings"]}
        self.assertEqual(details["coverage_missing"], "s2")
        self.assertEqual(details["coverage_extra"], "s3")

    def test_stale_map_sha(self):
        raw_doc = encode(document())
        pin = hashlib.sha256(raw_doc).hexdigest()
        other = "b" * 64
        receipt = receipt_for(raw_doc)
        receipt["map_sha256"] = other
        code, raw = m.assess_map(raw_doc, encode(receipt), pin, ALIASES)
        self.assertEqual(code, 1)
        self.assertIn("stale_map_sha", names((code, raw)))
        code, raw = m.assess_map(raw_doc, encode(receipt_for(raw_doc)), other, ALIASES)
        self.assertEqual(code, 1)
        self.assertIn("stale_map_sha", names((code, raw)))

    def test_author_alias_and_unicode_self_check(self):
        cases = [
            ("生产方", "生产方", None),
            ("producer", "Producer", None),
            ("producer", "pro\u200bducer", None),
            ("producer", "\uff50roducer", None),
            ("生产方", "producer", ALIASES),
            ("生产方", "Producer", ALIASES),
            ("producer", "生产方\u200b", ALIASES),
        ]
        for author, verifier, aliases in cases:
            code, raw = run(document([step()], author=author, verifier=verifier), aliases=aliases)
            self.assertEqual(code, 1, (author, verifier))
            self.assertIn("author_alias_self_check", names((code, raw)))

    def test_verifier_only_format_chars_is_missing(self):
        for verifier in ("", " \t", "\u200b", "\ufeff"):
            code, raw = run(document([step()], verifier=verifier), aliases=None)
            self.assertEqual(code, 1, repr(verifier))
            self.assertIn("verifier_not_independent", names((code, raw)))

    def test_distinct_names_pass(self):
        code, _ = run(document([step()], author="生产方", verifier="验收方\u200b"), aliases=None)
        self.assertEqual(code, 0)
        code, _ = run(document([step()], author="生产方", verifier="reviewer"))
        self.assertEqual(code, 0)

    def test_null_verifier_is_input_error(self):
        doc = document()
        doc["verifier"] = None
        self.assertEqual(run(doc)[0], 5)
        del doc["verifier"]
        self.assertEqual(run(doc)[0], 5)

    def test_malformed_inputs_are_input_errors(self):
        self.assertEqual(m.assess_map(b"", b"{}", "a" * 64, None)[0], 5)
        self.assertEqual(run(expected="zz")[0], 5)
        self.assertEqual(run(aliases=[])[0], 5)
        self.assertEqual(run(aliases={"生产方": ["验收方"], "验收方": ["生产方"]})[0], 5)
        doc = document()
        doc["steps"] = [step("s1"), step("s1")]
        self.assertEqual(run(doc)[0], 5)
        doc = document([step()])
        doc["status"] = "closed"
        self.assertEqual(run(doc)[0], 5)

    def test_missing_measured_source_is_a_finding(self):
        code, raw = run(document([step("s1", source="\u200b")]))
        self.assertEqual(code, 1)
        self.assertIn("missing_measured_source", names((code, raw)))

    def test_commands_are_not_executed(self):
        marker = Path(os.environ.get("TMPDIR", "/tmp")) / "loop-map-must-not-be-created"
        if marker.exists():
            marker.unlink()
        doc = document([step()])
        doc["steps"][0]["command"] = ["touch", str(marker)]
        code, _ = run(doc)
        self.assertEqual(code, 0)
        self.assertFalse(marker.exists())

    def test_output_is_canonical_and_sorted(self):
        doc = document([step("b"), step("a")])
        first = run(doc, ids=())
        second = run(doc, ids=())
        self.assertEqual(first, second)
        self.assertTrue(first[1].endswith(b"\n"))
        parsed = body(first)
        self.assertEqual([item["detail"] for item in parsed["findings"] if item["finding"] == "coverage_missing"],
                         ["a", "b"])
        self.assertEqual(first[1], (json.dumps(parsed, ensure_ascii=False, sort_keys=True,
                                               separators=(",", ":")) + "\n").encode())


class CapabilityMapTests(unittest.TestCase):
    def test_complete_capability_map_is_not_called_closed(self):
        source = "stdout sha256 " + "ab" * 32
        document = {
            "capability": "example/v1",
            "producer": "生产方",
            "steps": [{"id": "s1", "command": "python3 -m unittest", "expected": "exit 0",
                       "measured_source": source}],
            "independent_verification": {"status": "REPRODUCED", "verifier": "验收方", "head_sha": "abc"},
        }
        raw = encode(document)
        digest = hashlib.sha256(raw).hexdigest()
        receipt = {"schema_version": "loop-map-receipt/v1", "map_sha256": digest, "steps": [{"id": "s1"}]}
        code, out = m.assess_capability_map(raw, encode(receipt), digest, ALIASES)
        parsed = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(parsed["result"], "NO_REGRESSION")
        self.assertNotIn("CLOSED", parsed["result"])

    def test_non_reproduced_status_fails_when_receipt_and_sha_align(self):
        source = "stdout sha256 " + "ab" * 32
        for status in ("NOT_TESTED", "not_tested", "FAILED", "BLOCKED", "PASS"):
            document = {
                "capability": "example/v1",
                "producer": "生产方",
                "steps": [{"id": "s1", "command": "python3 -m unittest", "expected": "exit 0",
                           "measured_source": source}],
                "independent_verification": {"status": status, "verifier": "验收方", "head_sha": "abc"},
            }
            raw = encode(document)
            digest = hashlib.sha256(raw).hexdigest()
            receipt = {"schema_version": "loop-map-receipt/v1", "map_sha256": digest,
                       "steps": [{"id": "s1"}]}
            code, out = m.assess_capability_map(raw, encode(receipt), digest, ALIASES)
            parsed = json.loads(out)
            self.assertEqual(code, 1, status)
            self.assertEqual([item["finding"] for item in parsed["findings"]],
                             ["verifier_not_independent"], status)

    def test_not_tested_status_cannot_exit_zero(self):
        document = {
            "producer": "生产方",
            "steps": [{"id": "s1", "command": "true", "expected": "exit 0",
                       "measured_source": "observed stdout"}],
            "independent_verification": {"status": "NOT_TESTED", "verifier": "验收方", "head_sha": None},
        }
        raw = encode(document)
        code, out = m.assess_capability_map(raw, None, hashlib.sha256(raw).hexdigest(), None)
        self.assertEqual(code, 1)
        self.assertIn("verifier_not_independent", names((code, out)))
        self.assertEqual(body((code, out))["result"], "REGRESSION")

    def test_repo_feature_maps_are_not_reported_closed(self):
        root = Path(__file__).resolve().parents[3]
        paths = sorted((root / "capabilities").glob("*/feature-map.json"))
        self.assertGreaterEqual(len(paths), 5)
        for path in paths:
            code, out = m.assess_capability_map(path.read_bytes(), None, None, None)
            parsed = json.loads(out)
            self.assertEqual(code, 1, path.name)
            self.assertEqual(parsed["result"], "REGRESSION", path.name)
            self.assertNotIn("CLOSED", parsed["result"])


if __name__ == "__main__":
    unittest.main()
