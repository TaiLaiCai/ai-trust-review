import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "check.py"
FIX = ROOT / "fixtures"
HEAD = "1526ea1bc733612dba4f814ecb220ea2330e0646"
AUTHOR = "TaiLaiCai"


def run(*argv):
    return subprocess.run([sys.executable, str(CHECK), *argv],
                          capture_output=True, text=True, timeout=30)


class Gate(unittest.TestCase):
    def test_self_review_receipt_fails(self):
        p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                "--receipt", str(FIX / "receipt-self-review.json"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("REVIEW_INDEPENDENCE_VIOLATION", p.stdout)
        self.assertIn("self-review", p.stdout)

    def test_stale_head_receipt_fails(self):
        p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                "--receipt", str(FIX / "receipt-stale-head.json"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("stale head", p.stdout)

    def test_independent_head_bound_receipt_passes(self):
        p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                "--receipt", str(FIX / "receipt-valid.json"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["verdict"], "INDEPENDENT_AND_HEAD_BOUND")

    def test_producer_identity_also_forbidden(self):
        p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                "--producer", "Hermes-Bot",
                "--receipt", str(FIX / "receipt-valid.json"))
        self.assertEqual(p.returncode, 1)

    def test_missing_head_sha_is_insufficient_not_pass(self):
        body = json.loads((FIX / "receipt-valid.json").read_text())
        del body["head_sha"]
        tmp = FIX.parent / "tests" / "tmp-no-head.json"
        tmp.write_text(json.dumps(body))
        try:
            p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                    "--receipt", str(tmp))
            self.assertEqual(p.returncode, 1)
            self.assertIn("insufficient, not PASS", p.stdout)
        finally:
            tmp.unlink()

    def test_login_compare_is_case_insensitive(self):
        p = run("check", "--pr-author", "TAILAICAI", "--pr-head-sha", HEAD,
                "--receipt", str(FIX / "receipt-self-review.json"))
        self.assertEqual(p.returncode, 1)

    def test_bad_usage_exits_two(self):
        p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", "deadbeef",
                "--receipt", str(FIX / "receipt-valid.json"))
        self.assertEqual(p.returncode, 2)

    def test_version_flag(self):
        p = run("--version")
        self.assertEqual(p.returncode, 0)
        self.assertIn("review-independence/v1", p.stdout)


if __name__ == "__main__":
    unittest.main()
