import json
import re
import unittest
from pathlib import Path

CAPABILITY_DIR = Path(__file__).resolve().parents[1]
REQUIRED_CONTRACT_FIELDS = ["goal", "acceptance", "grants", "paths", "stop_when", "budget"]
REQUIRED_REGISTRATION_FIELDS = [
    "hypothesis",
    "criteria",
    "control_allocation",
    "random_seed",
    "expected_direction",
    "sample_size_statement",
]


class C3ExperimentTests(unittest.TestCase):
    def test_fixtures_are_valid_json_and_marked_demo(self):
        fixture_dir = CAPABILITY_DIR / "fixtures"
        files = sorted(fixture_dir.glob("*.json"))
        self.assertGreaterEqual(len(files), 1)
        for fixture_file in files:
            with self.subTest(fixture=fixture_file.name):
                data = json.loads(fixture_file.read_text(encoding="utf-8"))
                self.assertIs(data.get("demo"), True)
                self.assertIn("合成演示数据，非真实数据", data.get("note", ""))

    def test_experiment_fixture_has_registration_fields(self):
        data = json.loads(
            (CAPABILITY_DIR / "fixtures" / "experiment-registration-demo.json").read_text(
                encoding="utf-8"
            )
        )
        for field in REQUIRED_REGISTRATION_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, data)
        self.assertIs(data["frozen_before_release"], True)
        self.assertIsInstance(data["random_seed"], int)
        control = data["control_allocation"]
        self.assertIn("method", control)
        self.assertIn("control_songs", control)
        self.assertIn("treatment_songs", control)
        self.assertTrue(control["control_songs"])
        self.assertTrue(control["treatment_songs"])
        self.assertIn("不能推断因果", data["sample_size_statement"])

    def test_prompt_contains_frozen_contract_fields(self):
        text = (CAPABILITY_DIR / "prompt.md").read_text(encoding="utf-8")
        for field in REQUIRED_CONTRACT_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, text)
        self.assertIn("你在 Apo Labs 工作。", text)
        self.assertIn("【目标】让每次发行都成为能回答问题的数据", text)

    def test_feature_map_is_valid_json_and_not_tested(self):
        data = json.loads(
            (CAPABILITY_DIR / "feature-map.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["capability"], "c3-experiment/v1")
        self.assertTrue(data["steps"])
        verification = data["independent_verification"]
        self.assertEqual(verification["status"], "NOT_TESTED")
        self.assertIsNone(verification["verifier"])
        self.assertIsNone(verification["head_sha"])

    def test_readme_relative_links_point_to_existing_files(self):
        text = (CAPABILITY_DIR / "README.md").read_text(encoding="utf-8")
        links = re.findall(r"\]\(([^)]+)\)", text)
        self.assertTrue(links)
        for link in links:
            with self.subTest(link=link):
                self.assertTrue((CAPABILITY_DIR / link).exists(), link)


if __name__ == "__main__":
    unittest.main()
