#!/usr/bin/env python3
"""F2 回归：回滚备份必须在任何平台写入之前核对 before_sha256。

缺陷（修复前）：rollback 先把备份字节原子写上平台，之后才读回比对
before_sha256。备份损坏时平台已经被写坏，才报 rollback-failed，verify 随后
FAIL —— 「拒绝回滚」却留下了比不回滚更糟的平台状态。

本文件用真实 CLI 子进程断言真实退出码与真实 JSON 输出，不 mock 文件系统。
所有夹具都是仓库内的模拟平台文件，不含真实平台凭据。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.dirname(HERE)
CHECK = os.path.join(CAP, "check.py")
PY = sys.executable

CORRUPT = b"CORRUPTED-BACKUP-BYTES\n"


def run(*argv):
    return subprocess.run([PY, CHECK] + list(argv), capture_output=True, text=True,
                          timeout=60)


def payload(proc):
    return json.loads(proc.stdout.strip().splitlines()[-1])


class RollbackBackupBase(unittest.TestCase):
    """一个已成功应用的作业（bot-a：候选字节已上平台，备份完好）。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="f2-rollback-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.platform_dir = os.path.join(self.root, "platform")
        os.makedirs(self.platform_dir, exist_ok=True)
        self.write_platform("bot-a", 1)
        self.write_platform("bot-b", 1)
        cdir = os.path.join(self.root, "candidates")
        os.makedirs(cdir, exist_ok=True)
        self.write_json(os.path.join(cdir, "v1.json"),
                        {"candidate_version": "v1", "bot": "bot-a", "stage": 2,
                         "config": {"mode": "auto"}})
        self.write_json(os.path.join(self.root, "t1.json"),
                        {"id": "job-1", "seq": 0, "version": "durable-trigger/v1",
                         "target_bot": "bot-a", "candidate_version": "v1"})
        proc = run("baseline", "--root", self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run("approve", "--root", self.root, "--candidate-version", "v1",
                   "--approver", "tester")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run("enqueue", "--root", self.root,
                   "--trigger", os.path.join(self.root, "t1.json"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run("trigger", "--root", self.root, "--holder", "worker-1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.backup_path = os.path.join(self.root, "backups", "job-1.json")
        with open(self.backup_path, "rb") as fh:
            self.backup_bytes = fh.read()
        self.backup_sha = hashlib.sha256(self.backup_bytes).hexdigest()
        self.platform_path = os.path.join(self.platform_dir, "bot-a.json")
        with open(self.platform_path, "rb") as fh:
            self.applied_bytes = fh.read()
        self.applied_sha = hashlib.sha256(self.applied_bytes).hexdigest()

    def write_platform(self, bot, stage):
        self.write_json(os.path.join(self.platform_dir, bot + ".json"),
                        {"bot": bot, "stage": stage, "config": {"mode": "manual"}})

    def write_json(self, path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, sort_keys=True, separators=(",", ":"))
            fh.write("\n")

    def platform_bytes(self):
        with open(self.platform_path, "rb") as fh:
            return fh.read()

    def read_state(self):
        with open(os.path.join(self.root, "state.json"), "r", encoding="utf-8") as fh:
            return json.load(fh)

    def corrupt_backup(self):
        with open(self.backup_path, "wb") as fh:
            fh.write(CORRUPT)

    def assert_platform_untouched(self):
        self.assertEqual(self.platform_bytes(), self.applied_bytes)
        self.assertEqual(hashlib.sha256(self.platform_bytes()).hexdigest(),
                         self.applied_sha)

    def assert_job_still_applied(self):
        job = self.read_state()["jobs"]["job-1"]
        self.assertEqual(job["status"], "APPLIED")
        self.assertEqual(job["after_sha256"], self.applied_sha)


class TestCorruptedBackupIsRejectedBeforeAnyPlatformWrite(RollbackBackupBase):
    def test_corrupted_backup_leaves_platform_and_job_untouched(self):
        """旧实现：平台被写成损坏字节后才报 rollback-failed（红）。
        修复后：写入前核对，拒绝时平台与有效作业状态原样保留（绿）。"""
        self.corrupt_backup()
        proc = run("rollback", "--root", self.root, "--trigger-id", "job-1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "rollback-failed")
        self.assertEqual(out["expected_sha256"], self.backup_sha)
        self.assertNotEqual(out.get("backup_sha256"), self.backup_sha)
        # 平台字节没有被写入：仍等于应用后的候选字节。
        self.assert_platform_untouched()
        # 有效作业状态不变：仍 APPLIED，且 verify 不因平台损坏而 FAIL。
        self.assert_job_still_applied()
        proc = run("verify", "--root", self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["verdict"], "PASS")
        # 拒绝后备份本身未被改动，仍可人工修复后重试。
        with open(self.backup_path, "rb") as fh:
            self.assertEqual(fh.read(), CORRUPT)


class TestMissingBackupKeepsContractAndWritesNothing(RollbackBackupBase):
    def test_missing_backup_is_contract_error_without_platform_write(self):
        """备份缺失：保持既有契约退出码 2（contract error），零平台写入，
        不扩大契约 —— 旧行为本就如此，修复不得改变它。"""
        os.unlink(self.backup_path)
        proc = run("rollback", "--root", self.root, "--trigger-id", "job-1")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("contract error", proc.stderr)
        self.assertIn("backup", proc.stderr)
        self.assert_platform_untouched()
        self.assert_job_still_applied()
        proc = run("verify", "--root", self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["verdict"], "PASS")


class TestIntactBackupStillRollsBack(RollbackBackupBase):
    def test_intact_backup_still_restores_the_pre_apply_bytes(self):
        """对照组：备份完好时回滚照常成功，恢复应用前字节。"""
        proc = run("rollback", "--root", self.root, "--trigger-id", "job-1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "rolled-back")
        self.assertEqual(out["restored_sha256"], self.backup_sha)
        self.assertEqual(self.platform_bytes(), self.backup_bytes)
        job = self.read_state()["jobs"]["job-1"]
        self.assertEqual(job["status"], "ROLLED_BACK")
        proc = run("verify", "--root", self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
