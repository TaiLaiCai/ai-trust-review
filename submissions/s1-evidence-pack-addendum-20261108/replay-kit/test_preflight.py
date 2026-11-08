#!/usr/bin/env python3
"""红绿测试 for preflight.py：临时目录中缺 sample_fixed.json → exit 3；完整 → exit 0。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "preflight.py"
FIXTURES = ("status_tool.py", "test_status_tool.py", "sample_fixed.json", "README.md")


def run_in(dirname):
    return subprocess.run([sys.executable, str(SCRIPT), dirname],
                          capture_output=True, text=True)


class TestPreflight(unittest.TestCase):
    def test_red_missing_sample_fixed(self):
        with tempfile.TemporaryDirectory() as d:
            for name in FIXTURES:
                if name != "sample_fixed.json":
                    (Path(d) / name).write_text("x")
            p = run_in(d)
            self.assertEqual(p.returncode, 3)
            self.assertIn("sample_fixed.json", p.stderr)

    def test_green_all_present(self):
        with tempfile.TemporaryDirectory() as d:
            for name in FIXTURES:
                (Path(d) / name).write_text("x")
            p = run_in(d)
            self.assertEqual(p.returncode, 0)

    def test_red_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            p = run_in(d)
            self.assertEqual(p.returncode, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
