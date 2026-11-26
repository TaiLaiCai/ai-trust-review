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


def run_reviews(fixture, author=AUTHOR, head=HEAD, *extra):
    return run("reviews", "--pr-author", author, "--pr-head-sha", head,
               "--reviews-file", str(FIX / fixture), *extra)


class ReviewGate(unittest.TestCase):
    """Platform-authenticated path (Superagent P2 / Codex P1 fix)."""

    def test_no_reviews_fails_closed_not_green(self):
        p = run_reviews("reviews-empty.json")
        self.assertEqual(p.returncode, 1)
        self.assertIn("failing closed", p.stdout)
        self.assertIn("NOT_TESTED stays red", p.stdout)

    def test_author_self_approval_via_platform_ignored(self):
        p = run_reviews("reviews-self-only.json")
        self.assertEqual(p.returncode, 1)
        self.assertIn("self-review APPROVED", p.stdout)

    def test_producer_approval_via_platform_ignored(self):
        p = run("reviews", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                "--producer", "Hermes-Bot",
                "--reviews-file", str(FIX / "reviews-valid.json"))
        self.assertEqual(p.returncode, 1)

    def test_stale_commit_approval_fails(self):
        p = run_reviews("reviews-stale-commit.json")
        self.assertEqual(p.returncode, 1)
        self.assertIn("stale commit", p.stdout)

    def test_superseded_approval_fails(self):
        p = run_reviews("reviews-superseded.json")
        self.assertEqual(p.returncode, 1)
        self.assertIn("CHANGES_REQUESTED", p.stdout)

    def test_unreadable_reviews_payload_fails_closed(self):
        tmp = FIX.parent / "tests" / "tmp-bad-reviews.json"
        tmp.write_text("{not json")
        try:
            p = run_reviews(str(tmp))
            self.assertEqual(p.returncode, 1)
            self.assertIn("insufficient, not PASS", p.stdout)
        finally:
            tmp.unlink()

    def test_non_list_reviews_payload_fails_closed(self):
        tmp = FIX.parent / "tests" / "tmp-obj-reviews.json"
        tmp.write_text('{"user": {"login": "x"}}')
        try:
            p = run_reviews(str(tmp))
            self.assertEqual(p.returncode, 1)
            self.assertIn("must be a JSON list", p.stdout)
        finally:
            tmp.unlink()

    def test_valid_non_author_head_bound_approval_passes(self):
        p = run_reviews("reviews-valid.json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["verdict"], "INDEPENDENT_AND_HEAD_BOUND")

    def test_blank_author_in_reviews_mode_is_usage_error(self):
        p = run_reviews("reviews-valid.json", author="   ")
        self.assertEqual(p.returncode, 2)
        self.assertIn("USAGE", p.stdout)


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

    def test_blank_pr_author_is_usage_error(self):
        p = run("check", "--pr-author", "   ", "--pr-head-sha", HEAD,
                "--receipt", str(FIX / "receipt-self-review.json"))
        self.assertEqual(p.returncode, 2)
        self.assertIn("USAGE", p.stdout)
        self.assertNotIn("INDEPENDENT_AND_HEAD_BOUND", p.stdout)

    def test_wrong_schema_receipt_fails(self):
        body = json.loads((FIX / "receipt-valid.json").read_text())
        body["schema_version"] = "not-a-receipt/v9"
        tmp = FIX.parent / "tests" / "tmp-wrong-schema.json"
        tmp.write_text(json.dumps(body))
        try:
            p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                    "--receipt", str(tmp))
            self.assertEqual(p.returncode, 1)
            self.assertIn("not a rerun-receipt/v1 receipt", p.stdout)
        finally:
            tmp.unlink()

    def test_missing_runner_account_fails(self):
        body = json.loads((FIX / "receipt-valid.json").read_text())
        del body["runner"]["account"]
        tmp = FIX.parent / "tests" / "tmp-no-account.json"
        tmp.write_text(json.dumps(body))
        try:
            p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                    "--receipt", str(tmp))
            self.assertEqual(p.returncode, 1)
            self.assertIn("missing runner.account", p.stdout)
        finally:
            tmp.unlink()

    def test_bad_usage_exits_two(self):
        p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", "deadbeef",
                "--receipt", str(FIX / "receipt-valid.json"))
        self.assertEqual(p.returncode, 2)

    def test_version_flag(self):
        p = run("--version")
        self.assertEqual(p.returncode, 0)
        self.assertIn("review-independence/v1", p.stdout)

    def test_existing_check_contract_unchanged(self):
        # P3: the original receipt gate keeps its red/green contract.
        for fixture, code in (("receipt-self-review.json", 1),
                              ("receipt-stale-head.json", 1),
                              ("receipt-valid.json", 0)):
            p = run("check", "--pr-author", AUTHOR, "--pr-head-sha", HEAD,
                    "--receipt", str(FIX / fixture))
            self.assertEqual(p.returncode, code, fixture)


if __name__ == "__main__":
    unittest.main()
