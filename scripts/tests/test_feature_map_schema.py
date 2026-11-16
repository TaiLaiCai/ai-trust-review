"""Capability maps share the independent_verification triple, discovered by glob.

Schema alignment is not a re-run receipt. NOT_TESTED/null/null must not
become REPRODUCED because the object was added, and a genuinely verified
status must not be forced back to NOT_TESTED.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import check_repository


class FeatureMapSchemaTest(unittest.TestCase):
    def test_all_capability_maps_pass_the_check(self):
        check_repository.check_capability_feature_maps()

    def test_repository_contract_checks_the_maps(self):
        check_repository.main()

    def test_new_capability_map_is_checked_without_hardcoded_list(self):
        # A sixth legal map (three keys, NOT_TESTED/null/null) must pass.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            caps = root / "capabilities"
            for rel in check_repository.glob_capability_maps(check_repository.ROOT):
                data = json.loads((check_repository.ROOT / rel).read_text())
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(data))
            extra = caps / "new_capability"
            extra.mkdir(parents=True, exist_ok=True)
            (extra / "feature-map.json").write_text(
                json.dumps(
                    {
                        "independent_verification": {
                            "status": "NOT_TESTED",
                            "verifier": None,
                            "head_sha": None,
                        }
                    }
                )
            )
            check_repository.check_capability_feature_maps(root=root)

    def test_reproduced_with_null_verifier_is_rejected(self):
        with self.assertRaises(AssertionError):
            check_repository.require_valid_independent_verification(
                {"status": "REPRODUCED", "verifier": None, "head_sha": "abc"},
                "probe",
            )

    def test_not_tested_with_verifier_is_rejected(self):
        with self.assertRaises(AssertionError):
            check_repository.require_valid_independent_verification(
                {"status": "NOT_TESTED", "verifier": "someone", "head_sha": None},
                "probe",
            )

    def test_reproduced_with_verifier_and_head_passes(self):
        check_repository.require_valid_independent_verification(
            {"status": "REPRODUCED", "verifier": "someone", "head_sha": "abc123"},
            "probe",
        )

    def test_extra_or_reordered_keys_are_rejected(self):
        base = {"status": "NOT_TESTED", "verifier": None, "head_sha": None}
        with self.assertRaises(AssertionError):
            check_repository.require_valid_independent_verification(
                {**base, "receipt": "fabricated"},
                "probe",
            )
        with self.assertRaises(AssertionError):
            check_repository.require_valid_independent_verification(
                {"verifier": None, "status": "NOT_TESTED", "head_sha": None},
                "probe",
            )

    def test_review_readonly_keeps_its_other_review_fields(self):
        review = json.loads(
            (
                check_repository.ROOT / "capabilities/review_readonly/feature-map.json"
            ).read_text()
        )
        self.assertEqual(review["runtime_bot_integration"], "NOT_TESTED")
        self.assertEqual(review["independent_acceptance"], "NOT_TESTED")
        self.assertEqual(review["scope"], check_repository.REVIEW_READONLY_SCOPE)
        self.assertEqual(
            review["independent_verification"],
            {"status": "NOT_TESTED", "verifier": None, "head_sha": None},
        )


if __name__ == "__main__":
    unittest.main()
