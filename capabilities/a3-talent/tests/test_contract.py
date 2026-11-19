"""A3 人才库能力目录的格式与契约字段校验。

只校验文件格式与契约字段是否齐全，不对能力本身的信任状态作判定。
能力本身的独立验证状态见 feature-map.json，当前为 NOT_TESTED。
"""

import json
import unittest
from pathlib import Path

CAPABILITY_DIR = Path(__file__).resolve().parents[1]

REQUIRED_CONTRACT_FIELDS = (
    "goal",
    "acceptance",
    "grants",
    "paths",
    "stop_when",
    "budget",
)

REQUIRED_TALENT_FIELDS = (
    "talent_id",
    "name",
    "voice_features",
    "history_percentile",
    "availability",
    "constraints",
)

REQUIRED_VOICE_FEATURE_KEYS = (
    "timbre",
    "range",
    "style",
    "mood",
    "language",
)

FORBIDDEN_PRIVATE_FIELDS = (
    "id_number",
    "phone",
    "address",
    "itinerary",
    "身份证",
    "电话",
    "住址",
    "行程",
)


class FixtureTests(unittest.TestCase):
    def test_fixtures_are_demo_json(self):
        """fixtures 是合法 JSON，且标了 demo，注明为合成演示数据。"""
        fixture_dir = CAPABILITY_DIR / "fixtures"
        files = sorted(fixture_dir.glob("*.json"))
        self.assertGreaterEqual(len(files), 1, "fixtures 目录下至少要有一个 JSON 文件")
        for path in files:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)
                self.assertIs(data.get("demo"), True, "顶层 demo 字段须为 true")
                self.assertIn("合成演示数据，非真实数据", data.get("note", ""))

    def test_fixture_talent_has_all_fields(self):
        """演示人才含 §4.7 全部字段，声音特色五项齐全，低置信标注为待人审。"""
        path = CAPABILITY_DIR / "fixtures" / "demo-talent-pool.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        talent = data["talent"]
        for key in REQUIRED_TALENT_FIELDS:
            with self.subTest(field=key):
                self.assertIn(key, talent)
        for key in REQUIRED_VOICE_FEATURE_KEYS:
            with self.subTest(voice_feature=key):
                self.assertIn(key, talent["voice_features"])
        self.assertEqual(talent["review_status"], "待人审")
        self.assertIn("label_version", talent)

    def test_fixture_talent_has_no_private_fields(self):
        """演示人才档案里无身份证、电话、住址、私人行程等隐私字段。"""
        path = CAPABILITY_DIR / "fixtures" / "demo-talent-pool.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        talent = data["talent"]
        blob = json.dumps(talent, ensure_ascii=False)
        for key in FORBIDDEN_PRIVATE_FIELDS:
            with self.subTest(forbidden=key):
                self.assertNotIn(key, blob)


class PromptTests(unittest.TestCase):
    def test_prompt_has_frozen_contract_fields(self):
        """prompt.md 含 goal、acceptance、grants、paths、stop_when、budget 六个契约字段。"""
        text = (CAPABILITY_DIR / "prompt.md").read_text(encoding="utf-8")
        for field in REQUIRED_CONTRACT_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, text)

    def test_prompt_quotes_framework_sections(self):
        """prompt.md 含 §0 注入版与 §6 A3 专属契约的引用标记。"""
        text = (CAPABILITY_DIR / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("§0 注入版", text)
        self.assertIn("§6 A3 人才库专属契约", text)
        self.assertIn("新标注不覆盖旧标注", text)


class FeatureMapTests(unittest.TestCase):
    def test_feature_map_is_not_tested(self):
        """feature-map.json 是合法 JSON，且独立验证状态为 NOT_TESTED。"""
        path = CAPABILITY_DIR / "feature-map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["capability"], "a3-talent/v1")
        verification = data["independent_verification"]
        self.assertEqual(verification["status"], "NOT_TESTED")
        self.assertIsNone(verification["verifier"])
        self.assertIsNone(verification["head_sha"])

    def test_feature_map_steps_have_required_fields(self):
        """feature-map.json 的每一步含 id、command、expected、tests。"""
        data = json.loads((CAPABILITY_DIR / "feature-map.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["steps"]), 1)
        for step in data["steps"]:
            with self.subTest(step=step.get("id")):
                self.assertIn("id", step)
                self.assertIn("command", step)
                self.assertIn("expected", step)
                self.assertIsInstance(step["tests"], list)
                self.assertGreaterEqual(len(step["tests"]), 1)


class ReadmeTests(unittest.TestCase):
    def test_readme_states_not_tested(self):
        """README 写明独立复跑待完成，状态为 NOT_TESTED。"""
        text = (CAPABILITY_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("NOT_TESTED", text)
        self.assertIn("生产者≠验收者", text)


if __name__ == "__main__":
    unittest.main()
