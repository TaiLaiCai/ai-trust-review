import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "check.py"


class Contract(unittest.TestCase):
    def run_check(self, text=None, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=text,
                              capture_output=True, timeout=10)

    def assert_verdict(self, text, rc, verdict):
        p = self.run_check(text.encode())
        self.assertEqual(p.returncode, rc, p.stderr)
        self.assertEqual(json.loads(p.stdout)["verdict"], verdict)
        return json.loads(p.stdout)

    def test_unmentioned_conventions(self):
        self.assert_verdict("目标：计算样例总数", 0, "LEXICAL_CLEAR")

    def test_red_fixture_and_file_input(self):
        p = self.run_check(None, str(ROOT / "fixtures/undefined.txt"))
        self.assertEqual(p.returncode, 3)
        self.assertEqual(json.loads(p.stdout)["undefined"], ["老规矩"])

    def test_green_fixture_and_file_input(self):
        p = self.run_check(None, str(ROOT / "fixtures/defined.txt"))
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["verdict"], "LEXICAL_CLEAR")

    def test_all_default_terms_require_definition(self):
        for term in json.loads((ROOT / "terms.json").read_text()):
            out = self.assert_verdict("请" + term + "处理", 3, "NEEDS_CLARIFICATION")
            self.assertIn(term, out["undefined"])

    def test_partial_definition_still_blocks(self):
        self.assert_verdict('老规矩与照旧\n约定定义：{"老规矩":"写报告"}', 3, "NEEDS_CLARIFICATION")

    def test_empty_definition_blocks(self):
        self.assert_verdict('老规矩\n约定定义：{"老规矩":"  "}', 3, "NEEDS_CLARIFICATION")

    def test_recursive_and_cross_reference_blocks(self):
        for definition in ("按老规矩执行", "同上次", "照旧"):
            text = '老规矩\n约定定义：' + json.dumps({"老规矩": definition}, ensure_ascii=False)
            self.assert_verdict(text, 3, "NEEDS_CLARIFICATION")

    def test_bad_or_duplicate_definition_is_input_error(self):
        for definition in ('not JSON', '[]', '{"老规矩":"a","老规矩":"b"}', '{"老规矩":1}', '{"陌生词":"a"}'):
            self.assert_verdict("老规矩\n约定定义：" + definition, 5, "INPUT_ERROR")

    def test_multiple_definition_lines_rejected(self):
        self.assert_verdict('约定定义：{}\n约定定义：{}', 5, "INPUT_ERROR")

    def test_custom_terms_and_bad_config(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "terms.json"
            config.write_text('["既定方式"]')
            p = self.run_check("采用既定方式".encode(), "--terms", str(config))
            self.assertEqual(p.returncode, 3)
            for bad in ('[]', '{}', '[""]', '["x","x"]', '[1]', '[" x"]'):
                config.write_text(bad)
                p = self.run_check(b"input", "--terms", str(config))
                self.assertEqual(p.returncode, 5, bad)

    def test_size_utf8_and_file_errors(self):
        for raw in (b'\xff', b'x' * (256 * 1024 + 1)):
            p = self.run_check(raw)
            self.assertEqual((p.returncode, json.loads(p.stdout)["verdict"]), (5, "INPUT_ERROR"))
        self.assertEqual(self.run_check(None, '/nonexistent/review-input').returncode, 5)

    def test_argument_errors(self):
        self.assertEqual(self.run_check(None, '--unknown').returncode, 2)

    def test_shell_content_is_never_executed(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "marker"
            self.assert_verdict(f'目标：$(touch {marker}) `touch {marker}`', 0, "LEXICAL_CLEAR")
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
