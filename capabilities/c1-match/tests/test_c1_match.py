import json
import unittest
from pathlib import Path

CAPABILITY = Path(__file__).resolve().parents[1]


class C1MatchTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
