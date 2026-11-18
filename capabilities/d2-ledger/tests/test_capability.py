import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = ["goal", "acceptance", "grants", "paths", "stop_when", "budget"]


class D2LedgerTests(unittest.TestCase):
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
        self.assertIn("D2 账本", prompt)

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

    def test_no_real_ledger_characteristics(self):
        content_files = [ROOT / "README.md", ROOT / "prompt.md", ROOT / "feature-map.json"]
        content_files += sorted((ROOT / "fixtures").glob("*.json"))
        for path in content_files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertTrue("demo" in text.lower() or "演示" in text,
                                "内容文件须带 demo 标记，只含合成结构")
                self.assertIsNone(re.search(r"\d{6,}", text), "出现 6 位以上连续数字，疑似真实账号或流水号")
                self.assertIsNone(re.search(r"(银行账号|银行卡号|流水号)\s*[:：]\s*\d", text))
                self.assertIsNone(re.search(r"¥\s*\d{4,}", text), "出现疑似真实金额")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        prompt = (ROOT / "prompt.md").read_text(encoding="utf-8")
        for text in (readme, prompt):
            self.assertIn("待 D10 决定", text)
            self.assertIn("ESCALATE", text)
            self.assertIn("不含任何真实账本内容", text)


if __name__ == "__main__":
    unittest.main()
