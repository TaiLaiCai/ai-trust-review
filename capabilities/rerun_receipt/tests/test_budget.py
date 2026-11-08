"""证据字节预算的真实尺寸测试:单文件 64MiB 上限、总读取 256MiB 上限、恰好边界放行。

用稀疏文件(写 1 字节后截断)构造大证据,磁盘占用近零;verify 走真实哈希路径。
回执摘要按全零内容直接计算,与稀疏文件字节一致,不预填。
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check.py"
MiB = 1024 * 1024
SINGLE = 64 * MiB
TOTAL = 256 * MiB


def sparse(path, size):
    with open(path, "wb") as f:
        f.write(b"\0")
        f.truncate(size)


def sha_zeros(size):
    digest, chunk, remaining = hashlib.sha256(), b"\0" * (4 * MiB), size
    while remaining:
        take = min(remaining, len(chunk))
        digest.update(chunk[:take])
        remaining -= take
    return digest.hexdigest()


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.evidence = self.dir / "evidence"
        self.evidence.mkdir()

    def build(self, sizes):
        """sizes: {id: (stdout_bytes, stderr_bytes)};生成合法 manifest 与 receipts,摘要按全零内容实算。"""
        commands, receipts = [], []
        for ident, (out_size, err_size) in sizes.items():
            commands.append({"id": ident, "argv": ["true"], "expect_exit": 0})
            sparse(self.evidence / f"{ident}.stdout", out_size)
            sparse(self.evidence / f"{ident}.stderr", err_size)
            receipts.append({
                "id": ident, "argv": ["true"], "exit_code": 0,
                "stdout_sha256": sha_zeros(out_size),
                "stderr_sha256": sha_zeros(err_size),
                "started_at": "2026-11-08T00:00:00Z", "finished_at": "2026-11-08T00:00:01Z",
            })
        (self.dir / "manifest.json").write_text(json.dumps({
            "schema_version": "rerun-manifest/v1", "head_sha": "0" * 40, "commands": commands}))
        (self.dir / "receipts.json").write_text(json.dumps({
            "schema_version": "rerun-receipt/v1", "head_sha": "0" * 40,
            "generated_at": "2026-11-08T00:00:02Z",
            "runner": {"account": "t", "agent": "t", "model": "t", "os": "t", "python": "t"},
            "receipts": receipts}))

    def verify(self):
        return subprocess.run([sys.executable, str(SCRIPT), "verify",
                               str(self.dir / "manifest.json"), str(self.dir / "receipts.json"),
                               "--evidence", str(self.evidence)],
                              capture_output=True, text=True, timeout=300)

    def test_single_file_over_limit_fails(self):
        self.build({"big": (SINGLE + 1, 0)})
        result = self.verify()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(json.loads(result.stdout)["verdict"], "FAIL")

    def test_total_budget_over_fails_and_single_files_pass_alone(self):
        sizes = {f"p{i}": (63 * MiB, 0) for i in range(4)}
        sizes["tip"] = (8 * MiB, 0)  # 4×63MiB + 8MiB = 260MiB > 256MiB,单文件均低于 64MiB
        self.build(sizes)
        result = self.verify()
        self.assertEqual(result.returncode, 1, result.stdout)
        # 对照:去掉 tip 后总量 252MiB,应 PASS(证明触发的是总量预算而非单文件)
        (self.evidence / "tip.stdout").unlink()
        (self.evidence / "tip.stderr").unlink()
        manifest = json.loads((self.dir / "manifest.json").read_text())
        manifest["commands"] = [c for c in manifest["commands"] if c["id"] != "tip"]
        (self.dir / "manifest.json").write_text(json.dumps(manifest))
        receipts = json.loads((self.dir / "receipts.json").read_text())
        receipts["receipts"] = [r for r in receipts["receipts"] if r["id"] != "tip"]
        (self.dir / "receipts.json").write_text(json.dumps(receipts))
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["scope"], "receipts-plus-evidence-bytes")

    def test_single_file_exact_limit_passes(self):
        self.build({"edge": (SINGLE, 0)})
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
