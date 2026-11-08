"""M2 健康 CI 窗口与仍保留的 14 天口径不得互相覆盖。"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STANDARDS = ROOT / "docs/standards"


class M2WindowTest(unittest.TestCase):
    def test_m2_healthy_ci_window_is_seven_days(self):
        policy = json.loads((STANDARDS / "审查门槛.json").read_text())
        self.assertEqual(policy["automation"]["min_M2_healthy_ci_days"], 7)
        self.assertEqual(policy["stages"]["3"]["min_shadow_days"], 14)
        self.assertEqual(policy["stages"]["4"]["min_healthy_ci_days"], 30)
        text06 = (STANDARDS / "06-Dune与CI上线门禁.md").read_text()
        text00 = (STANDARDS / "00-入口与统一判定.md").read_text()
        text02 = (STANDARDS / "02-阶段2-自证正确.md").read_text()
        text03 = (STANDARDS / "03-阶段3-接收信号.md").read_text()
        self.assertIn("M2要求连续7个自然日", text06)
        self.assertNotIn("M2要求连续14个自然日", text06)
        self.assertIn("检测器审阅、7天CI、持久触发实测", text06)
        self.assertIn("flaky测试14天内翻转≥2次", text06)
        self.assertIn("阶段3另有14天/100真实信号的影子窗口", text06)
        self.assertIn("M2：CI 连续 7 天全绿", text00)
        self.assertIn("阶段 3：14 天、100 个真实影子信号", text00)
        self.assertIn("CI连续7天", text02)
        self.assertIn("连续14个自然日", text03)
        manifest = json.loads((STANDARDS / "source-manifest.json").read_text())
        self.assertEqual(
            manifest["original_source_sha256"]["06-Dune与CI上线门禁.md"],
            "53c46caa23555f96f0cf3ca8c23ee290574c308c266d3503d4de6570c28772ec",
        )
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("M2 窗口：连续 7 个自然日", workflow)
        self.assertIn("cron: '0 3 * * *'", workflow)
        self.assertNotIn("连续 14 个自然日", workflow)


if __name__ == "__main__":
    unittest.main()
