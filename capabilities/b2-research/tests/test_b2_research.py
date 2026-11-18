import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class B2ResearchTests(unittest.TestCase):
    def test_fixture_is_valid_json_and_marked_demo(self):
        fixtures = sorted((ROOT / "fixtures").glob("*.json"))
        self.assertGreaterEqual(len(fixtures), 1)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                data = json.loads(fixture.read_text(encoding="utf-8"))
                self.assertIs(data.get("demo"), True)
                self.assertIn("合成演示数据，非真实数据", data.get("note", ""))
                self.assertIn("演示", json.dumps(data, ensure_ascii=False))

    def test_prompt_contains_frozen_contract_fields(self):
        text = (ROOT / "prompt.md").read_text(encoding="utf-8")
        for field in ["goal", "acceptance", "grants", "paths", "stop_when", "budget"]:
            with self.subTest(field=field):
                self.assertIn(field, text)
        self.assertIn("rounds", text)
        self.assertIn("files", text)

    def test_prompt_contains_section_zero_and_b2_contract(self):
        text = (ROOT / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("你在 Apo Labs 工作。", text)
        self.assertIn("【目标】把零散激增归并成“一类特征在上升”，判定层级、阶段与剩余窗口。", text)
        self.assertIn("【验收】每个 hotspot 含层级、目标特征区间、阶段、窗口区间（上下界）、证据引用、样本量。", text)
        self.assertIn("确定性聚类出候选", text)

    def test_feature_map_is_valid_json_and_not_tested(self):
        data = json.loads((ROOT / "feature-map.json").read_text(encoding="utf-8"))
        self.assertEqual(data.get("capability"), "b2-research/v1")
        verification = data.get("independent_verification", {})
        self.assertEqual(verification.get("status"), "NOT_TESTED")
        self.assertIsNone(verification.get("verifier"))
        self.assertIsNone(verification.get("head_sha"))
        steps = data.get("steps", [])
        self.assertGreaterEqual(len(steps), 1)
        for step in steps:
            with self.subTest(step=step.get("id")):
                self.assertIn("id", step)
                self.assertIn("command", step)
                self.assertIn("expected", step)
                self.assertIn("tests", step)

    def test_readme_relative_links_point_to_existing_files(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        targets = re.findall(r"\]\(([^)]+)\)", text)
        self.assertGreaterEqual(len(targets), 1)
        for target in targets:
            with self.subTest(target=target):
                self.assertFalse(target.startswith("http"))
                path = target.split("#", 1)[0]
                self.assertTrue((ROOT / path).is_file(), target)


if __name__ == "__main__":
    unittest.main()
