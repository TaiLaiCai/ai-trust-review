"""A1 采集能力目录的格式与契约字段校验。

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

    def test_fixture_batch_counts_are_consistent(self):
        """演示批次的条数等于观测数加未解析数，结构可核对。"""
        path = fixture_dir = CAPABILITY_DIR / "fixtures" / "demo-source-batch.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        batch = data["batch"]
        self.assertEqual(
            batch["total_count"],
            len(data["observations"]) + batch["unparsed_count"],
        )
        self.assertEqual(batch["unparsed_count"], len(data["unparsed_queue"]))


class PromptTests(unittest.TestCase):
    def test_prompt_has_frozen_contract_fields(self):
        """prompt.md 含 goal、acceptance、grants、paths、stop_when、budget 六个契约字段。"""
        text = (CAPABILITY_DIR / "prompt.md").read_text(encoding="utf-8")
        for field in REQUIRED_CONTRACT_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, text)

    def test_prompt_quotes_framework_sections(self):
        """prompt.md 含 §0 注入版与 §6 A1 专属契约的引用标记。"""
        text = (CAPABILITY_DIR / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("§0 注入版", text)
        self.assertIn("§6 A1 采集专属契约", text)
        self.assertIn("纯确定性脚本，不用 LLM", text)


class FeatureMapTests(unittest.TestCase):
    def test_feature_map_is_not_tested(self):
        """feature-map.json 是合法 JSON，且独立验证状态为 NOT_TESTED。"""
        path = CAPABILITY_DIR / "feature-map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["capability"], "a1-collect/v1")
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
