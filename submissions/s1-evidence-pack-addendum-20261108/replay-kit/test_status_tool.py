#!/usr/bin/env python3
"""Unittest for status_tool.py. Runs the real script as a subprocess."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "status_tool.py"


def run(args=None, stdin=""):
    p = subprocess.run([sys.executable, str(SCRIPT)] + (args or []),
                       input=stdin, capture_output=True, text=True)
    return p


class TestStatusTool(unittest.TestCase):
    def test_fixed_sample(self):
        data = [{"status": "PASS"}, {"status": "FAIL"}, {"status": "BLOCKED"},
                {"status": "NOT_TESTED"}, {"status": "PASS"}]
        p = run(stdin=json.dumps(data))
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout),
                         {"PASS": 2, "FAIL": 1, "BLOCKED": 1, "NOT_TESTED": 1})

    def test_empty_array(self):
        p = run(stdin="[]")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout),
                         {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "NOT_TESTED": 0})

    def test_not_array(self):
        p = run(stdin='{"status": "PASS"}')
        self.assertEqual(p.returncode, 2)
        self.assertIn("not a JSON array", p.stderr)

    def test_missing_status(self):
        p = run(stdin='[{"name": "x"}]')
        self.assertEqual(p.returncode, 2)
        self.assertIn("missing 'status'", p.stderr)

    def test_unknown_status(self):
        p = run(stdin='[{"status": "NOPE"}]')
        self.assertEqual(p.returncode, 2)
        self.assertIn("unknown status", p.stderr)

    def test_invalid_json(self):
        p = run(stdin="not json")
        self.assertEqual(p.returncode, 2)

    def test_file_input(self):
        p = run(args=["--file", str(Path(__file__).parent / "sample_fixed.json")])
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout),
                         {"PASS": 2, "FAIL": 1, "BLOCKED": 1, "NOT_TESTED": 1})


if __name__ == "__main__":
    unittest.main(verbosity=2)
