import json
import unittest
from pathlib import Path

CAPABILITY = Path(__file__).resolve().parents[1]


class B3VerifyTests(unittest.TestCase):
    def test_fixtures_are_demo_json(self):
        fixtures = CAPABILITY / "fixtures"
        files = sorted(fixtures.glob("*.json"))
        self.assertGreaterEqual(len(files), 1, "至少 1 个合成演示输入")
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIs(data.get("demo"), True, f"{path.name} 须标 demo: true")
            self.assertIn("合成演示数据，非真实数据", str(data.get("note", "")))

    def test_prompt_has_frozen_contract_fields(self):
        text = (CAPABILITY / "prompt.md").read_text(encoding="utf-8")
        for field in ("goal", "acceptance", "grants", "paths", "stop_when", "budget"):
            self.assertIn(field, text, f"prompt.md 缺少契约字段 {field}")

    def test_feature_map_is_not_tested(self):
        data = json.loads((CAPABILITY / "feature-map.json").read_text(encoding="utf-8"))
        verification = data.get("independent_verification", {})
        self.assertEqual(verification.get("status"), "NOT_TESTED")
        self.assertIsNone(verification.get("verifier"))
        self.assertIsNone(verification.get("head_sha"))

    def test_independence_from_b2_stated(self):
        phrase = "与 B2 不得同一实例"
        prompt = (CAPABILITY / "prompt.md").read_text(encoding="utf-8")
        readme = (CAPABILITY / "README.md").read_text(encoding="utf-8")
        self.assertTrue(
            phrase in prompt or phrase in readme,
            "prompt.md 或 README.md 须含“与 B2 不得同一实例”",
        )
        self.assertIn(phrase, prompt, "prompt.md 须含独立性表述")
        self.assertIn(phrase, readme, "README.md 须含独立性表述")


if __name__ == "__main__":
    unittest.main()
