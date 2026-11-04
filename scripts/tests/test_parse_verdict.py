import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import parse_verdict

SCRIPT = SCRIPTS / "parse_verdict.py"


class ParseVerdictTest(unittest.TestCase):
    def test_extracts_each_verdict_from_a_comment(self):
        for verdict in parse_verdict.VERDICTS:
            text = "\n".join([
                "## 意图",
                "补一份公开格式",
                "## 结论",
                verdict,
                "一行摘要",
                "## 发现",
                "无。",
                f"VERDICT: {verdict}",
                "",
            ])
            self.assertEqual(parse_verdict.parse_verdict(text), verdict)

    def test_ignores_prose_and_accepts_a_stripped_line(self):
        text = "规格写作 VERDICT: 建议合并|需修改|阻塞 ，这不是裁决行。\n  VERDICT: 需修改  \n"
        self.assertEqual(parse_verdict.parse_verdict(text), "需修改")

    def test_missing_verdict_line(self):
        with self.assertRaises(parse_verdict.VerdictError) as caught:
            parse_verdict.parse_verdict("只有正文，没有裁决行。\n建议合并\n")
        self.assertEqual(caught.exception.code, "missing")

    def test_multiple_verdict_lines(self):
        text = "VERDICT: 建议合并\nVERDICT: 建议合并\n"
        with self.assertRaises(parse_verdict.VerdictError) as caught:
            parse_verdict.parse_verdict(text)
        self.assertEqual(caught.exception.code, "multiple")

    def test_invalid_verdict_value(self):
        for line in ("VERDICT: PASS", "VERDICT: 建议合并|需修改|阻塞", "VERDICT:"):
            with self.assertRaises(parse_verdict.VerdictError) as caught:
                parse_verdict.parse_verdict(line + "\n")
            self.assertEqual(caught.exception.code, "invalid", line)

    def test_cli_file_and_stdin(self):
        comment = "## 发现\n无。\n\nVERDICT: 阻塞\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comment.md"
            path.write_text(comment, encoding="utf-8")
            ok = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout, "阻塞\n")

        missing = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input="没有裁决行\n",
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(missing.stderr, "error: no verdict line\n")
        self.assertEqual(missing.stdout, "")

        multiple = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input="VERDICT: 需修改\nVERDICT: 阻塞\n",
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(multiple.returncode, 1)
        self.assertEqual(multiple.stderr, "error: multiple verdict lines\n")

        invalid = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input="VERDICT: PASS\n",
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(invalid.stderr, "error: invalid verdict\n")

        usage = subprocess.run(
            [sys.executable, str(SCRIPT), "a", "b"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(usage.returncode, 2)
        self.assertIn("usage:", usage.stderr)
