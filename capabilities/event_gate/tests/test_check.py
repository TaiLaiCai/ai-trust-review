import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(BASE, "check.py")
EXAMPLE = os.path.join(BASE, "example", "ledger.jsonl")


def run(*argv):
    p = subprocess.run([sys.executable, CHECK, *argv],
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def ev(i, eid="t%d" % 0, evidence="e" * 64, version="event-gate/v1"):
    return {"id": eid, "kind": "task", "version": version,
            "task_index": i, "evidence_sha256": evidence}


def write_ledger(path, records):
    prev = "0" * 64
    lines = []
    for r in records:
        r = dict(r)
        r["prev_sha256"] = prev
        line = canon(r) + "\n"
        lines.append(line)
        prev = hashlib.sha256(line.encode()).hexdigest()
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


class TestExampleAndVersion(unittest.TestCase):
    def test_version(self):
        rc, out, _ = run("--version")
        self.assertEqual(rc, 0)
        readme = hashlib.sha256(open(os.path.join(BASE, "README.md"), "rb").read()).hexdigest()
        self.assertIn(readme, out)

    def test_example_gate_pass(self):
        rc, out, _ = run("gate", EXAMPLE)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["verdict"], "PASS")

    def test_example_replay_noop(self):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "l.jsonl")
            with open(led, "wb") as f:
                f.write(open(EXAMPLE, "rb").read())
            rc, out, _ = run("apply", led,
                             json.dumps(ev(2, "task-c", "c" * 64)))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out)["action"], "replay-noop")
            self.assertEqual(open(led, "rb").read(), open(EXAMPLE, "rb").read())


class TestApply(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.led = os.path.join(self.d.name, "l.jsonl")
        write_ledger(self.led, [ev(0, "task-a", "a" * 64),
                                ev(1, "task-b", "b" * 64)])

    def tearDown(self):
        self.d.cleanup()

    def bytes(self):
        return open(self.led, "rb").read()

    def test_append(self):
        rc, out, _ = run("apply", self.led, json.dumps(ev(2, "task-c")))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["action"], "appended")
        self.assertEqual(len(self.bytes().splitlines()), 3)
        rc, _, _ = run("gate", self.led)
        self.assertEqual(rc, 0)

    def test_conflict_frozen(self):
        before = self.bytes()
        rc, out, _ = run("apply", self.led, json.dumps(ev(1, "task-b", "f" * 64)))
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["action"], "conflict-frozen")
        self.assertEqual(self.bytes(), before)

    def test_version_drift_rejected(self):
        before = self.bytes()
        rc, out, _ = run("apply", self.led, json.dumps(ev(2, "task-c", version="event-gate/v0")))
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["action"], "version-drift-invalid")
        self.assertEqual(self.bytes(), before)

    def test_index_gap_rejected(self):
        before = self.bytes()
        rc, out, _ = run("apply", self.led, json.dumps(ev(5, "task-x")))
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["action"], "index-gap-rejected")
        self.assertEqual(self.bytes(), before)

    def test_event_with_prev_rejected(self):
        e = ev(2, "task-c")
        e["prev_sha256"] = "0" * 64
        rc, _, err = run("apply", self.led, json.dumps(e))
        self.assertEqual(rc, 2)
        self.assertIn("prev_sha256", err)

    def test_append_to_broken_ledger_rejected(self):
        data = self.bytes().splitlines(keepends=True)
        data[0] = data[0].replace(b'"task-a"', b'"tampered"')
        with open(self.led, "wb") as f:
            f.writelines(data)
        before = open(self.led, "rb").read()
        rc, out, _ = run("apply", self.led, json.dumps(ev(2, "task-c")))
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["action"], "rejected")
        self.assertEqual(open(self.led, "rb").read(), before)


class TestGate(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.led = os.path.join(self.d.name, "l.jsonl")

    def tearDown(self):
        self.d.cleanup()

    def test_pass_three_consecutive(self):
        write_ledger(self.led, [ev(0, "a"), ev(1, "b"), ev(2, "c")])
        rc, out, _ = run("gate", self.led)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["task_indexes"], [0, 1, 2])

    def test_too_short(self):
        write_ledger(self.led, [ev(0, "a"), ev(1, "b")])
        rc, out, _ = run("gate", self.led)
        self.assertEqual(rc, 1)
        self.assertIn("chain-too-short", out)

    def test_missing_evidence_breaks_chain(self):
        e = ev(2, "c")
        del e["evidence_sha256"]
        write_ledger(self.led, [ev(0, "a"), ev(1, "b"), e])
        rc, out, _ = run("gate", self.led)
        self.assertEqual(rc, 1)
        self.assertIn("missing-evidence", out)

    def test_version_drift_in_ledger(self):
        write_ledger(self.led, [ev(0, "a"), ev(1, "b"),
                                ev(2, "c", version="event-gate/v2")])
        rc, out, _ = run("gate", self.led)
        self.assertEqual(rc, 1)
        self.assertIn("version-drift", out)

    def test_tampered_line_breaks_chain(self):
        write_ledger(self.led, [ev(0, "a"), ev(1, "b"), ev(2, "c")])
        data = open(self.led, "rb").read().splitlines(keepends=True)
        data[1] = data[1].replace(b"e" * 64, b"f" * 64)
        open(self.led, "wb").write(b"".join(data))
        rc, out, _ = run("gate", self.led)
        self.assertEqual(rc, 1)

    def test_index_gap_fails(self):
        write_ledger(self.led, [ev(0, "a"), ev(1, "b")])
        with open(self.led, "a", encoding="utf-8") as f:
            prev = hashlib.sha256(
                open(self.led, "rb").read().splitlines()[-1] + b"\n").hexdigest()
            f.write(canon(dict(ev(3, "c"), prev_sha256=prev)) + "\n")
        rc, out, _ = run("gate", self.led)
        self.assertEqual(rc, 1)
        self.assertIn("index-gap", out)

    def test_contract_error_exit_2(self):
        open(self.led, "w").write("not json\n")
        rc, _, err = run("gate", self.led)
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
