"""Five capability maps share unverified independent_verification keys.

Schema alignment is not a re-run receipt. NOT_TESTED/null/null must not
become REPRODUCED because the object was added.
"""
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import check_repository


class FeatureMapSchemaTest(unittest.TestCase):
    def test_five_capability_maps_stay_unverified(self):
        check_repository.check_capability_feature_maps()

    def test_repository_contract_checks_the_maps(self):
        check_repository.main()

    def test_reproduced_status_is_rejected(self):
        with self.assertRaises(AssertionError):
            check_repository.require_unverified_independent_verification(
                {"status": "REPRODUCED", "verifier": "someone", "head_sha": "abc"},
                "probe",
            )

    def test_extra_or_reordered_keys_are_rejected(self):
        base = {"status": "NOT_TESTED", "verifier": None, "head_sha": None}
        with self.assertRaises(AssertionError):
            check_repository.require_unverified_independent_verification(
                {**base, "receipt": "fabricated"},
                "probe",
            )
        with self.assertRaises(AssertionError):
            check_repository.require_unverified_independent_verification(
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
