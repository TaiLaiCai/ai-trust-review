import json
import re
import unittest
from pathlib import Path

CAPABILITY_DIR = Path(__file__).resolve().parents[1]
REQUIRED_CONTRACT_FIELDS = ["goal", "acceptance", "grants", "paths", "stop_when", "budget"]
EXPECTED_BRIEF_FIELDS = [
    "field_1_hotspot_name_and_level",
    "field_2_stage_and_window_deadline",
    "field_3_target_features",
    "field_4_evidence",
    "field_5_stock_match_result",
    "field_6_recommended_tier_and_deadline",
    "field_7_confidence_and_uncertainty",
    "field_8_prohibited_similarity_boundary",
    "field_9_acceptance_items",
]


class C2BriefTests(unittest.TestCase):
    def test_fixtures_are_valid_json_and_marked_demo(self):
        fixture_dir = CAPABILITY_DIR / "fixtures"
        files = sorted(fixture_dir.glob("*.json"))
        self.assertGreaterEqual(len(files), 1)
        for fixture_file in files:
            with self.subTest(fixture=fixture_file.name):
                data = json.loads(fixture_file.read_text(encoding="utf-8"))
                self.assertIs(data.get("demo"), True)
                self.assertIn("合成演示数据，非真实数据", data.get("note", ""))

    def test_brief_fixture_has_nine_fixed_fields(self):
        data = json.loads(
            (CAPABILITY_DIR / "fixtures" / "brief-input-demo.json").read_text(encoding="utf-8")
        )
        fields = data["fields"]
        self.assertEqual(len(fields), 9)
        for field_name in EXPECTED_BRIEF_FIELDS:
            with self.subTest(field=field_name):
                self.assertIn(field_name, fields)
        evidence = fields["field_4_evidence"]
        self.assertIn("platform", evidence)
        self.assertIn("growth_multiple", evidence)
        self.assertIn("fact_ids", evidence)
        self.assertTrue(evidence["fact_ids"])
        boundary = fields["field_8_prohibited_similarity_boundary"]
        self.assertIn("avoid_reference_types", boundary)
        self.assertTrue(boundary["avoid_reference_types"])

    def test_prompt_contains_frozen_contract_fields(self):
        text = (CAPABILITY_DIR / "prompt.md").read_text(encoding="utf-8")
        for field in REQUIRED_CONTRACT_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, text)
        self.assertIn("你在 Apo Labs 工作。", text)
        self.assertIn("【目标】一页简报，创作团队可直接开工", text)

    def test_feature_map_is_valid_json_and_not_tested(self):
        data = json.loads(
            (CAPABILITY_DIR / "feature-map.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["capability"], "c2-brief/v1")
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
