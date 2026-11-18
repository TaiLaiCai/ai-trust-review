import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADVANCE = ROOT / "advance.py"
sys.path.insert(0, str(ROOT))
import advance  # noqa: E402


def plan_for(input_bytes, units, plan_id="two-units"):
    document = {
        "schema": advance.SCHEMA,
        "plan_id": plan_id,
        "input_sha256": advance.sha256(input_bytes),
        "units": units,
    }
    return advance.canonical(document)


def unit(unit_id, code, expected, stdin=None):
    return {
        "id": unit_id,
        "argv": [sys.executable, "-c",
                 "from pathlib import Path; p=Path('marker'); p.write_text((p.read_text() if p.exists() else '')+'" + unit_id + "\\n'); import sys; sys.exit(" + str(code) + ")"],
        "stdin_sha256": None if stdin is None else advance.sha256(stdin),
        "expected_exit": expected,
    }


class AdvanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ledger = self.dir / "ledger.jsonl"
        self.bound = b"bound-version-1"
        self.cwd = self.dir / "work"
        self.cwd.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_plan(self, units, delivery="d1", input_bytes=None, max_steps=None, stdin=None):
        raw = plan_for(self.bound, units)
        return advance.advance(
            raw, self.bound if input_bytes is None else input_bytes,
            stdin or {}, self.ledger, delivery, self.cwd, max_steps,
        )

    def test_two_units_run_serially_in_one_process(self):
        result = self.run_plan([unit("U1", 0, 0), unit("U2", 0, 0)])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["executed"], ["U1", "U2"])
        self.assertEqual((self.cwd / "marker").read_text(), "U1\nU2\n")
        rows = advance.read_ledger(self.ledger)
        self.assertEqual([row["status"] for row in rows], ["claimed", "ok", "claimed", "ok"])
        self.assertEqual(rows[1]["prev_sha256"], advance.sha256(advance.canonical(rows[0])))

    def test_duplicate_delivery_does_not_execute_again(self):
        units = [unit("U1", 0, 0), unit("U2", 0, 0)]
        self.run_plan(units)
        again = self.run_plan(units)
        self.assertEqual(again["executed"], [])
        self.assertEqual(again["status"], "complete")
        self.assertEqual((self.cwd / "marker").read_text(), "U1\nU2\n")

    def test_process_exit_resumes_at_the_next_unit(self):
        raw = plan_for(self.bound, [unit("U1", 0, 0), unit("U2", 0, 0)])
        plan_path = self.dir / "plan.json"
        input_path = self.dir / "input.bin"
        plan_path.write_bytes(raw)
        input_path.write_bytes(self.bound)
        first = subprocess.run(
            [sys.executable, str(ADVANCE), "--plan", str(plan_path), "--input", str(input_path),
             "--ledger", str(self.ledger), "--delivery", "d1", "--cwd", str(self.cwd), "--max-steps", "1"],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual((self.cwd / "marker").read_text(), "U1\n")
        second = subprocess.run(
            [sys.executable, str(ADVANCE), "--plan", str(plan_path), "--input", str(input_path),
             "--ledger", str(self.ledger), "--delivery", "d1", "--cwd", str(self.cwd)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.cwd / "marker").read_text(), "U1\nU2\n")
        self.assertEqual(json.loads(second.stdout)["executed"], ["U2"])

    def test_mismatch_stops_and_a_later_delivery_does_not_continue(self):
        result = self.run_plan([unit("U1", 3, 0), unit("U2", 0, 0)])
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["executed"], ["U1"])
        self.assertFalse((self.cwd / "marker").read_text().count("U2"))
        again = self.run_plan([unit("U1", 3, 0), unit("U2", 0, 0)], delivery="d2")
        self.assertEqual(again["executed"], [])
        self.assertEqual(again["status"], "stopped")
        self.assertNotIn("U2", (self.cwd / "marker").read_text())

    def test_expected_exit_2_is_success_and_continues(self):
        result = self.run_plan([unit("U1", 2, 2), unit("U2", 0, 0)])
        self.assertEqual(result["status"], "complete")
        self.assertEqual((self.cwd / "marker").read_text(), "U1\nU2\n")

    def test_input_mismatch_executes_nothing(self):
        result = self.run_plan([unit("U1", 0, 0)], input_bytes=b"other-version")
        self.assertEqual(result["status"], "rejected")
        self.assertFalse((self.cwd / "marker").exists())
        rows = advance.read_ledger(self.ledger)
        self.assertEqual(rows[0]["status"], "rejected")

    def test_input_bytes_are_not_executed(self):
        hostile = b"DO_NOT_RUN import os; os.system('touch pwned')"
        raw = advance.canonical({
            "schema": advance.SCHEMA,
            "plan_id": "ignore-input-body",
            "input_sha256": advance.sha256(hostile),
            "units": [unit("U1", 0, 0)],
        })
        result = advance.advance(raw, hostile, {}, self.ledger, "d1", self.cwd, None)
        self.assertEqual(result["executed"], ["U1"])
        self.assertFalse((self.cwd / "pwned").exists())
        self.assertEqual((self.cwd / "marker").read_text(), "U1\n")


class Verdict6744651431Tests(unittest.TestCase):
    """裁决 6744631431/6744651431：改 argv 不得假完成；输入被拒要停；并发不双跑；空 stdin 可声明。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ledger = self.dir / "ledger.jsonl"
        self.bound = b"bound-version-1"
        self.cwd = self.dir / "work"
        self.cwd.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_raw(self, raw, delivery="d1", input_bytes=None, stdin=None):
        return advance.advance(
            raw, self.bound if input_bytes is None else input_bytes,
            stdin or {}, self.ledger, delivery, self.cwd, None,
        )

    def test_changed_argv_is_not_reported_complete(self):
        first = self.run_raw(plan_for(self.bound, [unit("U1", 0, 0)]))
        self.assertEqual(first["status"], "complete")
        marker = self.cwd / "argv-changed-marker"
        changed_units = [{
            "id": "U1",
            "argv": ["touch", str(marker)],
            "stdin_sha256": None,
            "expected_exit": 0,
        }]
        second = self.run_raw(plan_for(self.bound, changed_units), delivery="d2")
        self.assertEqual(second["status"], "stopped")
        self.assertEqual(second["executed"], [])
        self.assertFalse(marker.exists())
        self.assertIn("plan changed", second["reason"])

    def test_rejected_input_stops_the_plan(self):
        raw = plan_for(self.bound, [unit("U1", 0, 0)])
        rejected = self.run_raw(raw, input_bytes=b"wrong-input")
        self.assertEqual(rejected["status"], "rejected")
        rows = advance.read_ledger(self.ledger)
        # 拒绝记录归档到计划声明的 sha，另记实际 sha
        self.assertEqual(rows[0]["input_sha256"], advance.sha256(self.bound))
        self.assertEqual(rows[0]["actual_input_sha256"], advance.sha256(b"wrong-input"))
        corrected = self.run_raw(raw, delivery="d2")  # 同一投递换正确输入
        self.assertEqual(corrected["status"], "stopped")
        self.assertEqual(corrected["executed"], [])
        self.assertFalse((self.cwd / "marker").exists())

    def test_concurrent_deliveries_run_each_unit_once(self):
        runs = self.cwd / "runs"
        slow = [{
            "id": "U1",
            "argv": ["/bin/sh", "-c", f"echo run >> {runs}; sleep 1"],
            "stdin_sha256": None,
            "expected_exit": 0,
        }]
        raw = plan_for(self.bound, slow)
        plan_path = self.dir / "plan.json"
        input_path = self.dir / "input.bin"
        plan_path.write_bytes(raw)
        input_path.write_bytes(self.bound)
        procs = [subprocess.Popen(
            [sys.executable, str(ADVANCE), "--plan", str(plan_path), "--input", str(input_path),
             "--ledger", str(self.ledger), "--delivery", f"d{i}", "--cwd", str(self.cwd)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) for i in range(2)]
        outs = [p.communicate(timeout=30) for p in procs]
        for p, (out, err) in zip(procs, outs):
            self.assertEqual(p.returncode, 0, err)
            self.assertIn("complete", out)
        self.assertEqual(runs.read_text().count("run"), 1)
        ok_rows = [r for r in advance.read_ledger(self.ledger) if r["status"] == "ok"]
        self.assertEqual(len(ok_rows), 1)

    def test_declared_empty_stdin_is_accepted(self):
        empty_hash = advance.sha256(b"")
        u = unit("U1", 0, 0, stdin=b"")
        self.assertEqual(u["stdin_sha256"], empty_hash)
        result = self.run_raw(plan_for(self.bound, [u]), stdin={"U1": b""})
        self.assertEqual(result["status"], "complete")


class DeploySafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ledger = self.dir / "ledger.jsonl"
        self.bound = b"bound-version-1"
        self.cwd = self.dir / "work"
        self.cwd.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_units(self, units, fault=None, delivery="d1"):
        return advance.advance(
            plan_for(self.bound, units), self.bound, {}, self.ledger, delivery, self.cwd,
            None, fault,
        )

    def test_crash_after_exec_before_ledger_does_not_rerun(self):
        first = self.run_units([unit("U1", 0, 0)], fault="after_exec")
        self.assertEqual(first["executed"], ["U1"])
        self.assertEqual((self.cwd / "marker").read_text(), "U1\n")
        again = self.run_units([unit("U1", 0, 0)], delivery="d2")
        self.assertEqual(again["status"], "stopped")
        self.assertEqual(again["executed"], [])
        self.assertEqual(again["reason"], "uncertain claim; not re-executed")
        self.assertEqual((self.cwd / "marker").read_text(), "U1\n")
        third = self.run_units([unit("U1", 0, 0)], delivery="d3")
        self.assertEqual(third["executed"], [])
        self.assertEqual((self.cwd / "marker").read_text(), "U1\n")
        uncertain = [row for row in advance.read_ledger(self.ledger) if row["status"] == "uncertain"]
        self.assertEqual(len(uncertain), 1)

    def test_crash_after_claim_before_exec_does_not_start(self):
        first = self.run_units([unit("U1", 0, 0)], fault="after_claim")
        self.assertEqual(first["executed"], [])
        self.assertFalse((self.cwd / "marker").exists())
        again = self.run_units([unit("U1", 0, 0)])
        self.assertEqual(again["status"], "stopped")
        self.assertFalse((self.cwd / "marker").exists())

    def test_unfinished_argv_swap_does_not_run(self):
        raw = plan_for(self.bound, [unit("U1", 0, 0), unit("U2", 0, 0)])
        first = advance.advance(raw, self.bound, {}, self.ledger, "d1", self.cwd, max_steps=1)
        self.assertEqual(first["executed"], ["U1"])
        swapped = plan_for(self.bound, [unit("U1", 0, 0), {
            "id": "U2",
            "argv": [sys.executable, "-c", "from pathlib import Path; Path('swapped').write_text('x')"],
            "stdin_sha256": None,
            "expected_exit": 0,
        }])
        second = advance.advance(swapped, self.bound, {}, self.ledger, "d2", self.cwd, None)
        self.assertEqual(second["status"], "stopped")
        self.assertEqual(second["executed"], [])
        self.assertFalse((self.cwd / "swapped").exists())
        self.assertEqual((self.cwd / "marker").read_text(), "U1\n")

    def test_queue_once_runs_only_authorized_task(self):
        queue = self.dir / "queue"
        queue.mkdir()
        plan = queue / "plan.json"
        payload = queue / "input.bin"
        raw = plan_for(self.bound, [unit("U1", 0, 0)])
        plan.write_bytes(raw)
        payload.write_bytes(self.bound)
        # 未授权的计划文件不得被执行。
        idle = advance.serve(queue, once=True)
        self.assertEqual(idle["status"], "idle")
        work = queue / "work"
        work.mkdir()
        self.assertFalse((work / "marker").exists())
        auth = queue / "authorized.jsonl"
        before = (
            '{"plan":"plan.json","input":"input.bin","delivery":"d1","cwd":"work",'
            '"producer_version":"external-claude-not-sent",'
            '"reviewer_version":"external-codex-not-sent"}\n'
        )
        auth.write_text(before)
        ran = advance.serve(queue, once=True)
        self.assertEqual(ran["executed"], ["U1"])
        self.assertEqual(auth.read_text(), before)
        self.assertEqual((work / "marker").read_text(), "U1\n")
        rows = advance.read_ledger(queue / "ledger.jsonl")
        self.assertTrue(all(row["actor_role"] == "consumer" for row in rows))
        self.assertTrue(any(row.get("reviewer_version") == "external-codex-not-sent" for row in rows))
        again = advance.serve(queue, once=True)
        self.assertEqual(again["executed"], [])
        self.assertEqual((work / "marker").read_text(), "U1\n")

    def test_spawn_failure_does_not_strand_later_authorization(self):
        queue = self.dir / "queue"
        work = queue / "work"
        work.mkdir(parents=True)
        bad = queue / "bad.json"
        good = queue / "good.json"
        payload = queue / "input.bin"
        payload.write_bytes(self.bound)
        bad.write_bytes(plan_for(self.bound, [{
            "id": "U1",
            "argv": ["/no/such/bounded-advance-bin"],
            "stdin_sha256": None,
            "expected_exit": 0,
        }], plan_id="missing-bin"))
        good.write_bytes(plan_for(self.bound, [unit("U1", 0, 0)], plan_id="good-task"))
        auth = queue / "authorized.jsonl"
        text = (
            '{"plan":"bad.json","input":"input.bin","delivery":"bad","cwd":"work"}\n'
            '{"plan":"good.json","input":"input.bin","delivery":"good","cwd":"work"}\n'
        )
        auth.write_text(text)
        ran = advance.serve(queue, once=True)
        self.assertEqual(ran["executed"], ["U1"])
        self.assertEqual((work / "marker").read_text(), "U1\n")
        self.assertEqual(auth.read_text(), text)
        rows = advance.read_ledger(queue / "ledger.jsonl")
        self.assertTrue(any(row["status"] == "rejected" and row["detail"] == "spawn failed" for row in rows))
        again = advance.serve(queue, once=True)
        self.assertEqual(again["executed"], [])
        self.assertEqual((work / "marker").read_text(), "U1\n")

    def test_queue_waits_without_polling_until_authorized(self):
        queue = self.dir / "queue"
        queue.mkdir()
        proc = subprocess.Popen(
            [sys.executable, str(ADVANCE), "--queue", str(queue)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        ready = queue / "ready"
        for _ in range(50):
            if ready.exists() or proc.poll() is not None:
                break
            subprocess.run(["/bin/sleep", "0.05"], check=False)
        self.assertIsNone(proc.poll())
        self.assertTrue(ready.exists())
        work = queue / "work"
        work.mkdir()
        self.assertFalse((work / "marker").exists())
        plan = queue / "plan.json"
        payload = queue / "input.bin"
        plan.write_bytes(plan_for(self.bound, [unit("U1", 0, 0)]))
        payload.write_bytes(self.bound)
        (queue / "authorized.jsonl").write_text(
            '{"plan":"plan.json","input":"input.bin","delivery":"d1","cwd":"work"}\n'
        )
        wake = queue / "wake.fifo"
        fd = os.open(wake, os.O_WRONLY)
        try:
            os.write(fd, b"\n")
        finally:
            os.close(fd)
        for _ in range(50):
            if (work / "marker").exists() or proc.poll() is not None:
                break
            subprocess.run(["/bin/sleep", "0.05"], check=False)
        self.assertEqual((work / "marker").read_text(), "U1\n")
        self.assertIsNone(proc.poll())
        proc.terminate()
        proc.communicate(timeout=5)
        self.assertEqual(
            (queue / "authorized.jsonl").read_text().count("\n"), 1,
        )


if __name__ == "__main__":
    unittest.main()
