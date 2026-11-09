import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADVANCE = ROOT / "advance.py"
sys.path.insert(0, str(ROOT))
import advance  # noqa: E402


def plan_for(input_bytes, units):
    document = {
        "schema": advance.SCHEMA,
        "plan_id": "two-units",
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
        self.assertEqual([row["status"] for row in rows], ["ok", "ok"])
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


if __name__ == "__main__":
    unittest.main()
