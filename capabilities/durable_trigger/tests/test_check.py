#!/usr/bin/env python3
"""durable_trigger v2 回归测试。

每个测试都通过真实 CLI 子进程调用 check.py，断言真实退出码与真实 JSON 输出，
不 mock 文件系统。所有夹具都是本仓库内的模拟平台文件，不含真实平台凭据。
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


def run(*argv, **kwargs):
    proc = subprocess.run([PY, CHECK] + list(argv), capture_output=True, text=True,
                          timeout=60, **kwargs)
    return proc


def payload(proc):
    """Parse the JSON the tool printed on stdout."""
    return json.loads(proc.stdout.strip().splitlines()[-1])


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="durable-trigger-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.platform_dir = os.path.join(self.root, "platform")
        os.makedirs(self.platform_dir, exist_ok=True)
        for bot, stage in (("bot-a", 1), ("bot-b", 1), ("bot-c", 1)):
            self.write_platform(bot, stage)

    def write_platform(self, bot, stage, config=None):
        data = {"bot": bot, "stage": stage, "config": config or {"mode": "manual"}}
        with open(os.path.join(self.platform_dir, bot + ".json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True, separators=(",", ":"))
            fh.write("\n")

    def platform_bytes(self, bot):
        with open(os.path.join(self.platform_dir, bot + ".json"), "rb") as fh:
            return fh.read()

    def write_candidate(self, version, bot, stage, config=None):
        cdir = os.path.join(self.root, "candidates")
        os.makedirs(cdir, exist_ok=True)
        data = {"candidate_version": version, "bot": bot, "stage": stage,
                "config": config or {"mode": "auto"}}
        path = os.path.join(cdir, version + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
        return path

    def write_trigger_file(self, name, tid, seq, bot, version):
        path = os.path.join(self.root, name)
        data = {"id": tid, "seq": seq, "version": "durable-trigger/v1",
                "target_bot": bot, "candidate_version": version}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
        return path

    def enqueue(self, tid, seq, bot, version, name=None):
        path = self.write_trigger_file(name or (tid + ".json"), tid, seq, bot, version)
        return run("enqueue", "--root", self.root, "--trigger", path)

    def prepare(self, version="v1", bot="bot-a", stage=2):
        """Baseline + candidate + approval: everything an apply needs except the trigger."""
        self.write_candidate(version, bot, stage)
        proc = run("baseline", "--root", self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run("approve", "--root", self.root, "--candidate-version", version,
                   "--approver", "tester")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def trigger(self, *extra, **kwargs):
        holder = kwargs.pop("holder", "worker-1")
        return run("trigger", "--root", self.root, "--holder", holder, *extra)


class TestVersion(Base):
    def test_version_prints_v2_and_readme_sha256(self):
        proc = run("--version")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        parts = proc.stdout.strip().split()
        self.assertEqual(parts[0], "v2")
        self.assertEqual(len(parts), 2)
        readme = os.path.join(CAP, "README.md")
        with open(readme, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(parts[1], digest)

    def test_version_does_not_read_inputs(self):
        proc = run("--version")
        self.assertEqual(proc.stderr, "")


class TestQueue(Base):
    def test_enqueue_appends_and_reports_seq(self):
        proc = self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "enqueued")
        self.assertEqual(out["seq"], 0)

    def test_duplicate_delivery_is_a_noop(self):
        self.assertEqual(self.enqueue("t1", 0, "bot-a", "v1").returncode, 0)
        proc = self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "duplicate-noop")

    def test_same_id_different_content_is_frozen(self):
        self.assertEqual(self.enqueue("t1", 0, "bot-a", "v1").returncode, 0)
        proc = self.enqueue("t1", 0, "bot-b", "v1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "conflict-frozen")

    def test_a_seq_already_bound_to_another_id_is_frozen(self):
        self.assertEqual(self.enqueue("t1", 0, "bot-a", "v1").returncode, 0)
        proc = self.enqueue("t2", 0, "bot-a", "v1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "conflict-frozen")
        self.assertIn("t1", out["reason"])

    def test_a_late_seq_is_admitted_but_never_skipped(self):
        # Admission is append-only: a late trigger is kept, the consumer
        # refuses to skip the gap in front of it.
        self.assertEqual(self.enqueue("t2", 5, "bot-a", "v1").returncode, 0)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["cursor_seq"], -1)

    def test_unknown_field_is_a_contract_error(self):
        path = os.path.join(self.root, "bad.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"id":"t1","seq":0,"version":"durable-trigger/v1",'
                     '"target_bot":"bot-a","candidate_version":"v1","extra":1}\n')
        proc = run("enqueue", "--root", self.root, "--trigger", path)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown field", proc.stderr)

    def test_duplicate_json_key_is_a_contract_error(self):
        path = os.path.join(self.root, "dup.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"id":"t1","id":"t2","seq":0,"version":"durable-trigger/v1",'
                     '"target_bot":"bot-a","candidate_version":"v1"}\n')
        proc = run("enqueue", "--root", self.root, "--trigger", path)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("duplicate JSON key", proc.stderr)


class TestLeaseLock(Base):
    def test_live_lease_held_by_another_holder_is_refused(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        first = self.trigger("--lease-seconds", "300")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        # A second, different holder arrives while the lease is live.
        second = self.trigger("--lease-seconds", "300", holder="worker-2")
        self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
        self.assertEqual(payload(second)["action"], "lease-held")

    def test_stale_lease_token_is_refused(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger("--lease-token", "999")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "stale-lease")

    def test_expired_lease_is_taken_over_with_a_new_generation(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        # A lease that expires immediately: the next holder takes over.
        first = self.trigger("--lease-seconds", "0")
        self.assertIn(first.returncode, (0, 1), first.stdout + first.stderr)
        first_token = payload(run("status", "--root", self.root))["lease"]["token"]
        # The expired lease is taken over: a new holder gets a new generation.
        second = self.trigger("--lease-seconds", "300", holder="worker-2")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        lease = payload(run("status", "--root", self.root))["lease"]
        self.assertEqual(lease["holder"], "worker-2")
        self.assertGreater(lease["token"], first_token)

    def test_a_pending_job_is_resumed_after_the_lease_expires(self):
        # 回归用例（预审复现）：租约立刻过期且 APPLY 被注入失败后，
        # 作业停在 APPLY_PENDING。旧实现在这里把作业锁死在旧世代：
        # 再 trigger 得 stale-lease，rollback 得 rollback-unavailable，
        # 游标永远走不动。正确行为是：过期租约可以被接管并续作。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        failed = self.trigger("--lease-seconds", "0", "--inject-failure", "APPLY")
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLY_PENDING")
        self.assertEqual(state["cursor_seq"], -1)
        original = self.platform_bytes("bot-a")

        # 租约已过期：新持有者接管，作业必须能续作，而不是 stale-lease。
        resumed = self.trigger("--lease-seconds", "300", holder="worker-2")
        self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
        out = payload(resumed)
        self.assertEqual(out["action"], "applied")
        self.assertTrue(out["resumed"])
        self.assertEqual(out["seq"], 0)
        self.assertNotEqual(self.platform_bytes("bot-a"), original)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLIED")
        self.assertEqual(state["cursor_seq"], 0)

    def test_the_same_holder_resumes_after_its_own_lease_expires(self):
        # 预审在 806ceba 上的原路径：同一持有者、租约立刻过期、APPLY 注入失败，
        # 再由同一持有者 trigger，然后 rollback。不能只覆盖换一个持有者的接管。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        before = self.platform_bytes("bot-a")
        failed = self.trigger("--lease-seconds", "0", "--inject-failure", "APPLY")
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertEqual(payload(failed)["result"], "APPLY_PENDING")
        resumed = self.trigger("--lease-seconds", "300")
        self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
        out = payload(resumed)
        self.assertEqual(out["action"], "applied")
        self.assertTrue(out["resumed"])
        self.assertNotEqual(self.platform_bytes("bot-a"), before)
        rolled = run("rollback", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(rolled.returncode, 0, rolled.stdout + rolled.stderr)
        self.assertEqual(payload(rolled)["action"], "rolled-back")
        self.assertEqual(self.platform_bytes("bot-a"), before)

    def test_an_explicit_old_lease_token_does_not_resume_or_advance(self):
        # 过期后的接管可以续作；调用方显式传入的旧世代号仍然拒绝，且零写入。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        before = self.platform_bytes("bot-a")
        failed = self.trigger("--lease-seconds", "0", "--inject-failure", "APPLY")
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        recorded = payload(run("status", "--root", self.root))
        self.assertEqual(recorded["jobs"]["t1"]["status"], "APPLY_PENDING")
        self.assertEqual(recorded["cursor_seq"], -1)
        refused = self.trigger("--lease-seconds", "300", "--lease-token", "0")
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertEqual(payload(refused)["action"], "stale-lease")
        after = payload(run("status", "--root", self.root))
        self.assertEqual(after["lease"]["token"], recorded["lease"]["token"])
        self.assertEqual(after["lease"]["holder"], recorded["lease"]["holder"])
        self.assertEqual(after["jobs"]["t1"]["status"], "APPLY_PENDING")
        self.assertEqual(after["cursor_seq"], -1)
        self.assertEqual(self.platform_bytes("bot-a"), before)

    def test_a_pending_job_resumed_after_expiry_can_be_rolled_back(self):
        # 回归用例（预审复现）：续作成功后，rollback 必须可用，
        # 不能再返回 rollback-unavailable。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        before = self.platform_bytes("bot-a")
        self.assertEqual(self.trigger("--lease-seconds", "0",
                                      "--inject-failure", "APPLY").returncode, 1)
        self.assertEqual(self.trigger("--lease-seconds", "300",
                                      holder="worker-2").returncode, 0)
        proc = run("rollback", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "rolled-back")
        self.assertEqual(self.platform_bytes("bot-a"), before)

    def test_a_live_lease_still_blocks_a_second_holder(self):
        # fencing 的真正含义：租约还活着时，别人不能接管、不能续作。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        first = self.trigger("--lease-seconds", "300")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = self.trigger("--lease-seconds", "300", holder="worker-2")
        self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
        self.assertEqual(payload(second)["action"], "lease-held")

    def test_verify_reports_a_pending_job_with_no_live_lease(self):
        # 死锁必须能被 verify 看见，而不是静悄悄卡住。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger("--lease-seconds", "0",
                                      "--inject-failure", "APPLY").returncode, 1)
        proc = run("verify", "--root", self.root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertTrue(any("no live lease" in p for p in out["problems"]),
                        out["problems"])


class TestCursor(Base):
    def test_cursor_advances_only_on_a_successful_apply(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["cursor_seq"], 0)

    def test_cursor_does_not_advance_on_a_failed_apply(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger("--inject-failure", "APPLY")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["cursor_seq"], -1)

    def test_a_consumed_trigger_is_not_consumed_twice(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        before = self.platform_bytes("bot-a")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "no-work")
        self.assertEqual(self.platform_bytes("bot-a"), before)

    def test_duplicate_id_in_the_queue_is_consumed_once(self):
        # 准入门的第二次 enqueue 是 duplicate-noop，不会写出第二行。
        # 要锁住消费门「同一 id 只消费一次」，必须直接往队列追加第二行。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        queue = os.path.join(self.root, "queue.jsonl")
        with open(queue, "rb") as fh:
            first = fh.read()
        self.assertTrue(first.endswith(b"\n"))
        with open(queue, "ab") as fh:
            fh.write(first)
        with open(queue, "rb") as fh:
            self.assertEqual(fh.read().count(b"\n"), 2)
        before = self.platform_bytes("bot-a")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "applied")
        applied = self.platform_bytes("bot-a")
        self.assertNotEqual(applied, before)
        again = self.trigger()
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(payload(again)["action"], "no-work")
        self.assertEqual(self.platform_bytes("bot-a"), applied)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["cursor_seq"], 0)
        self.assertEqual(len(state["consumed"]), 1)
        with open(queue, "rb") as fh:
            self.assertEqual(fh.read().count(b"\n"), 2)

    def test_gap_in_the_queue_is_rejected_not_skipped(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        # seq 1 is missing; seq 2 arrives late. It may be admitted, but the
        # consumer must not skip the gap.
        self.assertEqual(self.enqueue("t3", 2, "bot-a", "v1").returncode, 0)
        # seq 0 is at the cursor, so it is consumed normally.
        first = self.trigger()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(payload(first)["seq"], 0)
        # Now the cursor is at 1, which is missing. seq 2 must not be skipped.
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "out-of-order-rejected")
        self.assertEqual(out["expected_seq"], 1)
        self.assertEqual(out["missing_seq"], 1)
        self.assertEqual(out["next_available_seq"], 2)
        # The cursor did not move past the gap.
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["cursor_seq"], 0)

    def test_a_late_trigger_is_consumed_once_the_gap_is_filled(self):
        self.prepare()
        for version, stage in (("v2", 3), ("v3", 4)):
            self.write_candidate(version, "bot-a", stage)
            proc = run("approve", "--root", self.root,
                       "--candidate-version", version, "--approver", "tester")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.enqueue("t3", 2, "bot-a", "v3").returncode, 0)
        self.assertEqual(self.trigger().returncode, 0)
        # The gap is still open: seq 2 is not consumed.
        self.assertEqual(self.trigger().returncode, 1)
        self.assertEqual(self.enqueue("t2", 1, "bot-a", "v2").returncode, 0)
        # The gap is filled; the consumer now advances in order.
        second = self.trigger()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(payload(second)["seq"], 1)
        third = self.trigger()
        self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
        self.assertEqual(payload(third)["seq"], 2)


class TestRestartContinuation(Base):
    def test_a_failed_apply_is_resumed_by_the_next_trigger(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        failed = self.trigger("--inject-failure", "APPLY")
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertEqual(payload(failed)["result"], "APPLY_PENDING")
        # Nothing was applied: the platform file still holds its original bytes.
        original = self.platform_bytes("bot-a")
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLY_PENDING")
        self.assertEqual(state["cursor_seq"], -1)
        # The next trigger resumes the pending job.
        resumed = self.trigger()
        self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
        out = payload(resumed)
        self.assertEqual(out["action"], "applied")
        self.assertTrue(out["resumed"])
        self.assertEqual(out["seq"], 0)
        self.assertNotEqual(self.platform_bytes("bot-a"), original)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLIED")
        self.assertEqual(state["cursor_seq"], 0)

    def test_resume_refuses_when_the_target_drifted(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        failed = self.trigger("--inject-failure", "APPLY")
        self.assertEqual(failed.returncode, 1)
        # Somebody else changes the target bot between the failure and the resume.
        self.write_platform("bot-a", 3, {"mode": "manual-edit"})
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "conflict-frozen")
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLY_PENDING")


class TestAtomicApplyAndReadback(Base):
    def test_apply_replaces_the_platform_file_and_reads_it_back(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "applied")
        self.assertEqual(out["readback_sha256"], out["after_sha256"])
        data = json.loads(self.platform_bytes("bot-a"))
        self.assertEqual(data["stage"], 2)
        self.assertEqual(data["config"]["mode"], "auto")

    def test_readback_mismatch_is_detected_and_rolled_back(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        before = self.platform_bytes("bot-a")
        proc = self.trigger("--inject-failure", "READBACK")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "readback-mismatch")
        self.assertEqual(out["result"], "APPLY_PENDING")
        # The target must be restored to its pre-apply bytes.
        self.assertEqual(self.platform_bytes("bot-a"), before)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLY_PENDING")

    def test_apply_without_approval_stays_apply_pending(self):
        self.write_candidate("v1", "bot-a", 2)
        run("baseline", "--root", self.root)
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "approval-missing")
        self.assertEqual(out["result"], "APPLY_PENDING")

    def test_candidate_changed_after_approval_is_refused(self):
        self.prepare()
        # The approved candidate bytes are edited behind the tool's back.
        self.write_candidate("v1", "bot-a", 4)
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "stale-candidate")
        self.assertEqual(out["result"], "APPLY_PENDING")

    def test_apply_writes_an_audit_entry(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        audit_path = os.path.join(self.root, "audit.jsonl")
        with open(audit_path, encoding="utf-8") as fh:
            entries = [json.loads(l) for l in fh if l.strip()]
        applied = [e for e in entries if e["action"] == "applied"]
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]["result"], "APPLIED")
        self.assertTrue(applied[0]["other_bots_unchanged"])


class TestOtherBotsUnchanged(Base):
    def test_other_bots_are_untouched_by_an_apply(self):
        self.prepare()
        before_b = self.platform_bytes("bot-b")
        before_c = self.platform_bytes("bot-c")
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(payload(proc)["other_bots_unchanged"])
        self.assertEqual(self.platform_bytes("bot-b"), before_b)
        self.assertEqual(self.platform_bytes("bot-c"), before_c)

    def test_a_changed_other_bot_blocks_the_apply(self):
        self.prepare()
        self.write_platform("bot-b", 2, {"mode": "someone-else"})
        self.enqueue("t1", 0, "bot-a", "v1")
        before_a = self.platform_bytes("bot-a")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "other-bot-changed")
        self.assertIn("bot-b", out["drifted_bots"])
        # The target must not have been touched.
        self.assertEqual(self.platform_bytes("bot-a"), before_a)

    def test_a_bot_outside_the_baseline_blocks_the_apply(self):
        self.prepare()
        self.write_platform("bot-d", 1)
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "other-bot-changed")
        self.assertIn("bot-d", out["unknown_bots"])

    def test_a_missing_target_outside_the_baseline_is_not_created(self):
        # 预审路径：基线里没有 bot-new，平台文件也不存在。旧实现会 applied
        # 把文件写出来，随后 verify 因 baseline 外 Bot 失败。
        self.prepare()
        self.write_candidate("v-new", "bot-new", 2)
        approved = run("approve", "--root", self.root, "--candidate-version", "v-new",
                       "--approver", "tester")
        self.assertEqual(approved.returncode, 0, approved.stdout + approved.stderr)
        self.assertEqual(self.enqueue("tn", 0, "bot-new", "v-new").returncode, 0)
        path = os.path.join(self.platform_dir, "bot-new.json")
        self.assertFalse(os.path.exists(path))
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "other-bot-changed")
        self.assertEqual(out["result"], "APPLY_PENDING")
        self.assertIn("bot-new", out["unknown_bots"])
        self.assertFalse(os.path.exists(path))
        ver = run("verify", "--root", self.root)
        self.assertEqual(ver.returncode, 0, ver.stdout + ver.stderr)
        self.assertEqual(payload(ver)["verdict"], "PASS")
        self.assertNotIn("outside the baseline", ver.stdout)

    def test_an_existing_target_outside_the_baseline_is_not_overwritten(self):
        self.prepare()
        self.write_platform("bot-new", 1)
        before = self.platform_bytes("bot-new")
        self.write_candidate("v-new", "bot-new", 2)
        approved = run("approve", "--root", self.root, "--candidate-version", "v-new",
                       "--approver", "tester")
        self.assertEqual(approved.returncode, 0, approved.stdout + approved.stderr)
        self.assertEqual(self.enqueue("tn", 0, "bot-new", "v-new").returncode, 0)
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "other-bot-changed")
        self.assertIn("bot-new", out["unknown_bots"])
        self.assertEqual(self.platform_bytes("bot-new"), before)

    def test_an_other_bot_drift_after_the_apply_is_rolled_back(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        before_a = self.platform_bytes("bot-a")
        proc = self.trigger("--inject-failure", "OTHER_BOT")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "other-bot-changed")
        self.assertEqual(out["result"], "APPLY_PENDING")
        self.assertEqual(self.platform_bytes("bot-a"), before_a)


class TestFailureRecovery(Base):
    def test_kill_switch_blocks_new_applies(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        engaged = run("kill-switch", "--root", self.root, "--engage", "--reason", "drill")
        self.assertEqual(engaged.returncode, 0, engaged.stdout + engaged.stderr)
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "kill-switch-engaged")
        self.assertEqual(out["result"], "APPLY_PENDING")
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLY_PENDING")

    def test_kill_switch_release_allows_applies_again(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        run("kill-switch", "--root", self.root, "--engage", "--reason", "drill")
        self.assertEqual(self.trigger().returncode, 1)
        released = run("kill-switch", "--root", self.root, "--release")
        self.assertEqual(released.returncode, 0, released.stdout + released.stderr)
        proc = self.trigger()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "applied")

    def test_rollback_restores_the_pre_apply_bytes(self):
        self.prepare()
        before = self.platform_bytes("bot-a")
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        self.assertNotEqual(self.platform_bytes("bot-a"), before)
        proc = run("rollback", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "rolled-back")
        self.assertEqual(self.platform_bytes("bot-a"), before)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "ROLLED_BACK")

    def test_rollback_is_allowed_while_the_kill_switch_is_engaged(self):
        self.prepare()
        before = self.platform_bytes("bot-a")
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        run("kill-switch", "--root", self.root, "--engage", "--reason", "drill")
        proc = run("rollback", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.platform_bytes("bot-a"), before)

    def test_rollback_of_a_never_applied_job_is_unavailable(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = run("rollback", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "rollback-unavailable")

    def test_rollback_of_an_older_job_does_not_clobber_a_newer_apply(self):
        self.prepare()
        self.write_candidate("v2", "bot-a", 3)
        approved = run("approve", "--root", self.root, "--candidate-version", "v2",
                       "--approver", "tester")
        self.assertEqual(approved.returncode, 0, approved.stdout + approved.stderr)
        self.enqueue("t1", 0, "bot-a", "v1")
        self.enqueue("t2", 1, "bot-a", "v2")
        self.assertEqual(self.trigger().returncode, 0)
        self.assertEqual(self.trigger().returncode, 0)
        newer = self.platform_bytes("bot-a")
        refused = run("rollback", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        out = payload(refused)
        self.assertEqual(out["action"], "rollback-unavailable")
        self.assertIn("t2", out["newer_jobs"])
        self.assertEqual(self.platform_bytes("bot-a"), newer)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLIED")
        self.assertEqual(state["jobs"]["t2"]["status"], "APPLIED")
        ver = run("verify", "--root", self.root)
        self.assertEqual(ver.returncode, 0, ver.stdout + ver.stderr)
        rolled_new = run("rollback", "--root", self.root, "--trigger-id", "t2")
        self.assertEqual(rolled_new.returncode, 0, rolled_new.stdout + rolled_new.stderr)
        rolled_old = run("rollback", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(rolled_old.returncode, 0, rolled_old.stdout + rolled_old.stderr)
        ver = run("verify", "--root", self.root)
        self.assertEqual(ver.returncode, 0, ver.stdout + ver.stderr)

    def test_a_second_rollback_is_a_noop(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        self.assertEqual(run("rollback", "--root", self.root, "--trigger-id", "t1").returncode, 0)
        proc = run("rollback", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "already-rolled-back")

    def test_a_failed_apply_is_never_reported_as_applied(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        proc = self.trigger("--inject-failure", "APPLY")
        self.assertEqual(proc.returncode, 1)
        out = payload(proc)
        self.assertNotEqual(out.get("result"), "APPLIED")
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLY_PENDING")


class TestAbort(Base):
    def test_abort_unblocks_a_pending_job_and_advances_the_cursor(self):
        # 最后一道人工出口：卡住的作业必须能被中止，游标才能继续往前走。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        before = self.platform_bytes("bot-a")
        self.assertEqual(self.trigger("--lease-seconds", "0",
                                      "--inject-failure", "APPLY").returncode, 1)
        proc = run("abort", "--root", self.root, "--trigger-id", "t1",
                   "--reason", "operator-gave-up")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "aborted")
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "ABORTED")
        self.assertEqual(state["cursor_seq"], 0)
        # 平台字节没有被改动过（中止不写入候选）。
        self.assertEqual(self.platform_bytes("bot-a"), before)

    def test_the_cursor_moves_past_an_aborted_job(self):
        self.prepare()
        for version, stage in (("v2", 3),):
            self.write_candidate(version, "bot-a", stage)
            run("approve", "--root", self.root,
                "--candidate-version", version, "--approver", "tester")
        self.enqueue("t1", 0, "bot-a", "v1")
        self.enqueue("t2", 1, "bot-a", "v2")
        self.assertEqual(self.trigger("--lease-seconds", "0",
                                      "--inject-failure", "APPLY").returncode, 1)
        self.assertEqual(run("abort", "--root", self.root,
                             "--trigger-id", "t1").returncode, 0)
        # 下一格现在可以正常消费。
        proc = self.trigger()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["seq"], 1)

    def test_abort_without_a_before_state_does_not_delete_the_target(self):
        # 批准缺失发生在记录应用前快照之前。before_present 为 null，
        # 中止不得把 null 当成「文件原本不存在」而删掉目标。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        # Drop the approval after baseline so the refusal happens first.
        state_path = os.path.join(self.root, "state.json")
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        state["approvals"] = {}
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
        before = self.platform_bytes("bot-a")
        refused = self.trigger()
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertEqual(payload(refused)["action"], "approval-missing")
        recorded = payload(run("status", "--root", self.root))
        self.assertIsNone(recorded["jobs"]["t1"]["before_present"])
        proc = run("abort", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(payload(proc)["platform_restored"])
        self.assertEqual(self.platform_bytes("bot-a"), before)
        self.assertTrue(os.path.exists(os.path.join(self.platform_dir, "bot-a.json")))

    def test_abort_of_a_non_pending_job_is_unavailable(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        proc = run("abort", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "abort-unavailable")

    def test_a_second_abort_is_a_noop(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger("--lease-seconds", "0",
                                      "--inject-failure", "APPLY").returncode, 1)
        self.assertEqual(run("abort", "--root", self.root,
                             "--trigger-id", "t1").returncode, 0)
        proc = run("abort", "--root", self.root, "--trigger-id", "t1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["action"], "already-aborted")


class TestCrashRecoveryAndAudit(Base):
    def test_a_crash_after_the_rename_is_recovered_not_frozen(self):
        # 崩溃窗口：rename 已落地、状态还没写。此时平台字节等于候选字节，
        # 不能当成「别人改了目标」而拒绝（那会把游标永久卡死），
        # 也不能重复应用；必须读回确认后补齐状态。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        applied_bytes = self.platform_bytes("bot-a")
        # 把状态倒回「应用前 + APPLY_PENDING」，模拟状态写入前崩溃。
        state_path = os.path.join(self.root, "state.json")
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        job = state["jobs"]["t1"]
        job["status"] = "APPLY_PENDING"
        job["after_sha256"] = None
        job["reason"] = "crashed-before-state-write"
        state["cursor_seq"] = -1
        state["consumed"] = {}
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True, separators=(",", ":"))

        proc = self.trigger()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "applied")
        self.assertTrue(out["recovered_after_crash"])
        # 平台字节没有被重复写入，也没有被回滚。
        self.assertEqual(self.platform_bytes("bot-a"), applied_bytes)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLIED")
        self.assertEqual(state["cursor_seq"], 0)

    def test_crash_recovery_refuses_when_another_bot_drifted(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        original = self.platform_bytes("bot-a")
        self.assertEqual(self.trigger().returncode, 0)
        state_path = os.path.join(self.root, "state.json")
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        job = state["jobs"]["t1"]
        job["status"] = "APPLY_PENDING"
        job["after_sha256"] = None
        job["reason"] = "crashed-before-state-write"
        state["cursor_seq"] = -1
        state["consumed"] = {}
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True, separators=(",", ":"))
        self.write_platform("bot-b", 9, {"mode": "changed-during-crash"})
        proc = self.trigger()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["action"], "other-bot-changed")
        self.assertEqual(out["result"], "APPLY_PENDING")
        self.assertIn("bot-b", out["drifted_bots"])
        self.assertNotEqual(out.get("action"), "applied")
        self.assertEqual(self.platform_bytes("bot-a"), original)
        state = payload(run("status", "--root", self.root))
        self.assertEqual(state["jobs"]["t1"]["status"], "APPLY_PENDING")
        self.assertEqual(state["cursor_seq"], -1)

    def test_a_non_utf8_audit_is_a_contract_error(self):
        # 退出码表把编码错误定为 2，与队列同一条 ContractError 路径。
        # 拿掉 load_audit 里的转换后，这里会变成未捕获的 UnicodeDecodeError（退出码 1）。
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        with open(os.path.join(self.root, "audit.jsonl"), "ab") as fh:
            fh.write(b'{"action":"x","ts":"\xff\xfe"}\n')
        proc = run("verify", "--root", self.root)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("audit: not valid UTF-8", proc.stderr)
        self.assertNotIn("UnicodeDecodeError", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class TestVerify(Base):
    def test_verify_passes_on_a_clean_root(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        proc = run("verify", "--root", self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = payload(proc)
        self.assertEqual(out["verdict"], "PASS")
        self.assertEqual(out["scope"], "state-queue-platform-audit-bytes-only")

    def test_verify_passes_after_a_rollback(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        self.assertEqual(run("rollback", "--root", self.root,
                             "--trigger-id", "t1").returncode, 0)
        proc = run("verify", "--root", self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["verdict"], "PASS")

    def test_verify_detects_platform_drift(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        self.write_platform("bot-b", 9, {"mode": "tampered"})
        proc = run("verify", "--root", self.root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(payload(proc)["verdict"], "FAIL")

    def test_verify_does_not_write(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v1")
        self.assertEqual(self.trigger().returncode, 0)
        before = sorted(os.listdir(self.root))
        mtimes = {n: os.stat(os.path.join(self.root, n)).st_mtime for n in before}
        self.assertEqual(run("verify", "--root", self.root).returncode, 0)
        after = sorted(os.listdir(self.root))
        self.assertEqual(before, after)
        for name in before:
            self.assertEqual(mtimes[name],
                             os.stat(os.path.join(self.root, name)).st_mtime)


class TestCliErrors(Base):
    def test_unknown_subcommand_is_a_usage_error(self):
        proc = run("nope", "--root", self.root)
        self.assertEqual(proc.returncode, 2)

    def test_missing_required_argument_is_a_usage_error(self):
        proc = run("enqueue", "--root", self.root)
        self.assertEqual(proc.returncode, 2)

    def test_a_missing_candidate_is_a_contract_error(self):
        self.prepare()
        self.enqueue("t1", 0, "bot-a", "v-nonexistent")
        proc = self.trigger()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not found", proc.stderr)


if __name__ == "__main__":
    unittest.main()
