import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = ["goal", "acceptance", "grants", "paths", "stop_when", "budget"]


class D1BackfillTests(unittest.TestCase):
    def test_fixtures_are_demo_json(self):
        fixtures = sorted((ROOT / "fixtures").glob("*.json"))
        self.assertTrue(fixtures, "fixtures 目录至少含 1 个合成演示输入")
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                data = json.loads(fixture.read_text(encoding="utf-8"))
                self.assertIs(data.get("demo"), True)
                self.assertIn("合成演示数据，非真实数据", str(data.get("note", "")))

    def test_prompt_contains_frozen_contract_fields(self):
        prompt = (ROOT / "prompt.md").read_text(encoding="utf-8")
        for field in REQUIRED_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, prompt)
        self.assertIn("你在 Apo Labs 工作。", prompt)
        self.assertIn("D1 回填", prompt)

    def test_feature_map_not_tested(self):
        feature_map = json.loads((ROOT / "feature-map.json").read_text(encoding="utf-8"))
        self.assertEqual(feature_map["independent_verification"]["status"], "NOT_TESTED")
        self.assertIsNone(feature_map["independent_verification"]["verifier"])
        self.assertIsNone(feature_map["independent_verification"]["head_sha"])
        self.assertTrue(feature_map.get("steps"))

    def test_readme_links_resolve(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        links = re.findall(r"\]\(([^)]+)\)", readme)
        relative = [link for link in links if not link.startswith(("http://", "https://", "#"))]
        self.assertTrue(relative, "README.md 至少含 1 个相对链接")
        for link in relative:
            with self.subTest(link=link):
                self.assertTrue((ROOT / link).is_file(), f"相对链接未指向实际文件：{link}")

    def test_no_self_signed_pass(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("NOT_TESTED", readme)
        self.assertNotIn("验收通过", readme)
        feature_map = json.loads((ROOT / "feature-map.json").read_text(encoding="utf-8"))
        self.assertNotEqual(feature_map["independent_verification"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
