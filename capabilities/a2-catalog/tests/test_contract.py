"""A2 作品库能力目录的格式与契约字段校验。

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

REQUIRED_FEATURE_KEYS = (
    "genre",
    "bpm",
    "mode",
    "mood",
    "theme",
    "vocal",
    "duration_seconds",
    "history_percentile",
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

    def test_fixture_work_has_all_features(self):
        """演示作品含各平台 ID 与全部八类特征，低置信标注为待人审。"""
        path = CAPABILITY_DIR / "fixtures" / "demo-work-catalog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        work = data["work"]
        self.assertGreaterEqual(len(work["platform_ids"]), 1)
        for key in REQUIRED_FEATURE_KEYS:
            with self.subTest(feature=key):
                self.assertIn(key, work["features"])
        self.assertEqual(work["review_status"], "待人审")
        self.assertIn("label_version", work)


class PromptTests(unittest.TestCase):
    def test_prompt_has_frozen_contract_fields(self):
        """prompt.md 含 goal、acceptance、grants、paths、stop_when、budget 六个契约字段。"""
        text = (CAPABILITY_DIR / "prompt.md").read_text(encoding="utf-8")
        for field in REQUIRED_CONTRACT_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, text)

    def test_prompt_quotes_framework_sections(self):
        """prompt.md 含 §0 注入版与 §6 A2 专属契约的引用标记。"""
        text = (CAPABILITY_DIR / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("§0 注入版", text)
        self.assertIn("§6 A2 作品库专属契约", text)
        self.assertIn("新标注不覆盖旧标注", text)


class FeatureMapTests(unittest.TestCase):
    def test_feature_map_is_not_tested(self):
        """feature-map.json 是合法 JSON，且独立验证状态为 NOT_TESTED。"""
        path = CAPABILITY_DIR / "feature-map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["capability"], "a2-catalog/v1")
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
