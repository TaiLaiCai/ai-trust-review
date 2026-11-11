"""Replay the detector-review checklist in docs/standards/06-Dune与CI上线门禁.md.

Each test name is the replay for one checklist item. Exit 0 is not closure.
History cases call control/loop_status unchanged. Real git roots, real
closed-loop reports, and a joint loop_closure+loop_status hookup are not
claimed here.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[3]
CAP = REPO / "capabilities" / "loop_closure"
HISTORY_PATH = REPO / "control" / "loop_status" / "history.py"

T1 = "2026-11-02T09:00+08:00"
T2 = "2026-11-02T10:00+08:00"
T3 = "2026-11-02T11:00+08:00"
HEAD = "a" * 40
OLD = "a" * 64
NEW = "b" * 64
OWNERS = {"owner": ["主人"], "worker": ["执行者"]}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


detect = load(CAP / "detect.py", "replay_detect")
maps = load(CAP / "map_coverage.py", "replay_map")
registry = load(CAP / "registry.py", "replay_registry")
history = load(HISTORY_PATH, "replay_history")


def encode(value, newline=False):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return raw + b"\n" if newline else raw


def step():
    return {"id": "s1", "command": ["true"], "exit_code": 0,
            "output_sha256": hashlib.sha256(b"ok\n").hexdigest(),
            "citations": [{"path": "a.txt", "line": 1, "excerpt": "hello"}]}


def closure_report(steps, verifier="验收方"):
    return {"schema_version": "loop-closure/v1", "head_sha": HEAD, "producer": "生产方",
            "verifier": verifier, "status": "closed", "loops": ["L1"], "steps": steps}


def assess_closure(report):
    return detect.assess(encode(report), {"a.txt": b"hello\n"}, {"s1": b"ok\n"}, HEAD, [])


def map_pair(ids, receipt_ids, author="生产方", verifier="验收方", pin=None, aliases=None):
    document = {"schema_version": "loop-map/v1", "author": author, "verifier": verifier, "steps": [
        {"id": sid, "command": ["python3", "-m", "unittest"], "expected": "exit 0",
         "measured_source": "stdout sha256 " + OLD} for sid in ids]}
    raw = encode(document)
    digest = hashlib.sha256(raw).hexdigest()
    receipt = {"schema_version": "loop-map-receipt/v1", "map_sha256": digest,
               "steps": [{"id": sid} for sid in receipt_ids]}
    return maps.assess_map(raw, encode(receipt), digest if pin is None else pin, aliases)


def chain(states):
    snapshots, lines, previous = {}, [], "0" * 64
    for number, (ts, loops) in enumerate(states, 1):
        sid = "snapshot-" + str(number)
        snapshots[sid] = encode({"ts": ts, "loops": loops}, newline=True)
        line = encode({"seq": number, "prev_sha256": previous, "snapshot_id": sid,
                       "sha256": hashlib.sha256(snapshots[sid]).hexdigest()}, newline=True).rstrip(b"\n")
        previous = hashlib.sha256(line).hexdigest()
        lines.append(line + b"\n")
    # previous is the last line without its LF, matching history.py's checkpoint.
    return snapshots, b"".join(lines), previous, len(lines)


def ratchet(snapshots, ledger, current, ts, waivers=None, owner_names=None, subject="worker",
            head=None, min_seq=None):
    lines = ledger.splitlines()
    if head is None:
        head = hashlib.sha256(lines[-1]).hexdigest() if lines else history.ZERO
    if min_seq is None:
        min_seq = len(lines)
    return history.assess(
        snapshots, ledger, current, ts, [] if waivers is None else waivers, OWNERS,
        ["owner"] if owner_names is None else owner_names, subject=subject,
        expected_head_sha256=head, min_seq=min_seq)


def parsed(result):
    return json.loads(result[1])


class DetectorReplay(unittest.TestCase):
    def test_replay_empty_steps(self):
        code, raw = assess_closure(closure_report([]))
        self.assertEqual(code, 1)
        self.assertIn("empty_steps", [item["finding"] for item in parsed((code, raw))["findings"]])
        self.assertEqual(parsed((code, raw))["status_ignored"], "closed")

    def test_replay_missing_coverage(self):
        code, raw = map_pair(("s1", "s2"), ("s1",))
        self.assertEqual(code, 1)
        findings = parsed((code, raw))["findings"]
        self.assertIn({"finding": "coverage_missing", "detail": "s2"}, findings)

    def test_replay_verifier_missing_or_null(self):
        code, raw = assess_closure(closure_report([step()], verifier=""))
        self.assertEqual(code, 1)
        self.assertIn("verifier_not_independent", [item["finding"] for item in parsed((code, raw))["findings"]])
        report = closure_report([step()])
        report["verifier"] = None
        code, raw = assess_closure(report)
        self.assertEqual(code, 5)
        self.assertEqual(parsed((code, raw))["result"], "INPUT_ERROR")
        self.assertNotEqual(code, 0)

    def test_replay_author_alias_self_check(self):
        aliases = {"生产方": ["producer", "\uff50roducer"], "验收方": ["reviewer"]}
        for author, verifier in (("生产方", "producer"), ("producer", "\uff50roducer"), ("生产方", "生产方\u200b")):
            code, raw = map_pair(("s1",), ("s1",), author=author, verifier=verifier, aliases=aliases)
            self.assertEqual(code, 1, (author, verifier))
            self.assertIn("author_alias_self_check", [item["finding"] for item in parsed((code, raw))["findings"]])
        code, _ = map_pair(("s1",), ("s1",), author="生产方", verifier="reviewer", aliases=aliases)
        self.assertEqual(code, 0)

    def test_replay_stale_map_sha(self):
        code, raw = map_pair(("s1",), ("s1",), pin="c" * 64)
        self.assertEqual(code, 1)
        self.assertIn("stale_map_sha", [item["finding"] for item in parsed((code, raw))["findings"]])

    def test_replay_hidden_table_column(self):
        headers = list(registry.REQUIRED_COLUMNS)
        headers[3] = "<!-- test_registration -->"
        row = ["C-1", "true", "hard", "pkg/tests/test_x.py::test_ok", OLD, NEW, "apo", T1]
        text = "\n".join([
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            "| " + " | ".join(row) + " |",
        ]) + "\n"
        known = {"pkg/tests/test_x.py::test_ok": b"def test_ok(self):\n    pass\n"}
        code, raw = registry.assess_registry_table(text, known)
        self.assertEqual(code, 1)
        self.assertIn("hidden_table_column", [item["finding"] for item in parsed((code, raw))["findings"]])
        self.assertEqual(parsed((code, raw))["result"], "REGRESSION")

    def test_replay_missing_or_empty_test_name(self):
        known = {"pkg/tests/test_x.py::test_ok": b"def test_ok(self):\n    pass\n"}

        def entry(eid, test, ts):
            return {"id": eid, "closed": True, "fix_kind": "hard", "test_registration": test,
                    "old_impl_sha256": OLD, "new_impl_sha256": NEW, "registered_by": "apo", "closed_at": ts}

        raw = encode({"schema_version": "correction-index/v1", "entries": [
            entry("C-1", "", T1),
            entry("C-2", "pkg/tests/test_x.py::test_absent", T2),
        ]})
        code, out = registry.assess_index(raw, known)
        self.assertEqual(code, 1)
        got = [item["finding"] for item in parsed((code, out))["findings"]]
        self.assertIn("empty_test_name", got)
        self.assertIn("missing_test_name", got)
        self.assertEqual(parsed((code, out))["old_impl_red_green"], "NOT_TESTED")

    def test_replay_nonmonotonic_timestamps(self):
        snaps, ledger, _, _ = chain([
            ("2026-11-02T10:00+08:00", {"A": "closed"}),
            ("2026-11-02T09:00+08:00", {"A": "closed"}),
        ])
        code, raw = ratchet(snaps, ledger, {"A": "closed"}, T3)
        self.assertEqual(code, 5)
        self.assertIn("strictly increasing", parsed((code, raw))["reason"])
        self.assertNotEqual(code, 1)

    def test_replay_time_travel(self):
        # 18:00+08 is earlier than 12:00Z, but the clock text sorts later.
        self.assertGreater("2026-11-02T18:00+08:00", "2026-11-02T12:00+00:00")
        snaps, ledger, _, _ = chain([("2026-11-02T12:00+00:00", {"A": "closed"})])
        code, raw = ratchet(snaps, ledger, {"A": "closed"}, "2026-11-02T18:00+08:00")
        self.assertEqual(code, 5)
        self.assertEqual(parsed((code, raw))["result"], "INPUT_ERROR")
        # 02:00Z is later than 09:00+08 even though the clock text sorts earlier.
        self.assertLess("2026-11-02T02:00+00:00", "2026-11-02T09:00+08:00")
        snaps, ledger, _, _ = chain([(T1, {"A": "closed"})])
        code, raw = ratchet(snaps, ledger, {"A": "closed"}, "2026-11-02T02:00+00:00")
        self.assertEqual(code, 0)
        self.assertEqual(parsed((code, raw))["result"], "NO_REGRESSION")

    def test_replay_deleted_history(self):
        snaps, ledger, head, count = chain([(T1, {"A": "closed"}), (T2, {"A": "open"})])
        kept = ledger.splitlines(keepends=True)[1]
        code, raw = ratchet(snaps, kept, {"A": "closed"}, T3, head=head, min_seq=count)
        self.assertEqual(code, 5)
        self.assertEqual(parsed((code, raw))["result"], "INPUT_ERROR")
        self.assertNotEqual(code, 0)

    def test_replay_duplicate_snapshots(self):
        snaps, ledger, _, _ = chain([(T1, {"A": "closed"}), (T2, {"A": "closed"})])
        rows = [json.loads(line) for line in ledger.splitlines()]
        rows[1]["snapshot_id"] = rows[0]["snapshot_id"]
        rebuilt = b"".join(encode(row, newline=True) for row in rows)
        head = hashlib.sha256(rebuilt.splitlines()[-1]).hexdigest()
        code, raw = ratchet(snaps, rebuilt, {"A": "closed"}, T3, head=head, min_seq=2)
        self.assertEqual(code, 5)
        self.assertIn("duplicate", parsed((code, raw))["reason"])

    def test_replay_self_written_waiver(self):
        for owners, subject in ((["执行者"], "worker"), (["worker"], "执行者"), (["主人"], "主人"),
                                (["\uff57orker"], "worker"), (["wor\u200bker"], "worker"),
                                (["worker\u200b"], "执行者")):
            code, raw = ratchet({}, b"", {"A": "open"}, T3, owner_names=owners, subject=subject)
            self.assertEqual(code, 5, (owners, subject))
            self.assertIn("own waiver", parsed((code, raw))["reason"])
        code, raw = ratchet({}, b"", {"A": "open"}, T3, owner_names=["\u200b"], subject="worker")
        self.assertEqual(code, 5)
        self.assertEqual(parsed((code, raw))["result"], "INPUT_ERROR")
        self.assertNotIn("own waiver", parsed((code, raw))["reason"])
        code, raw = ratchet({}, b"", {"A": "open"}, T3, owner_names=["主人"], subject="worker")
        self.assertEqual(code, 0)
        self.assertEqual(parsed((code, raw))["result"], "NO_REGRESSION")
        code, raw = ratchet({}, b"", {"A": "open"}, T3, owner_names=["\uff4fwner"], subject="执行者\u200b")
        self.assertEqual((code, parsed((code, raw))["result"]), (0, "NO_REGRESSION"))

    def test_replay_output_order(self):
        raw_snap = (json.dumps({"loops": {"Z": "closed", "A": "closed"}, "ts": T1},
                               ensure_ascii=False) + "\n").encode()
        sid = "snapshot-1"
        line = encode({"prev_sha256": "0" * 64, "seq": 1, "sha256": hashlib.sha256(raw_snap).hexdigest(),
                       "snapshot_id": sid}, newline=True).rstrip(b"\n")
        ledger = line + b"\n"
        head = hashlib.sha256(line).hexdigest()
        current = {}
        current["Z"] = "open"
        current["A"] = "open"
        code, raw = ratchet({sid: raw_snap}, ledger, current, T3, head=head, min_seq=1)
        body = parsed((code, raw))
        self.assertEqual(code, 1)
        self.assertEqual(body["regressions"], ["A", "Z"])
        self.assertEqual(list(body["loops"]), ["A", "Z"])
        again = {}
        again["A"] = "open"
        again["Z"] = "open"
        self.assertEqual(raw, ratchet({sid: bytes(raw_snap)}, bytes(ledger), again, T3, head=head, min_seq=1)[1])
        code, map_raw = map_pair(("b", "a"), ())
        details = [item["detail"] for item in parsed((code, map_raw))["findings"]
                   if item["finding"] == "coverage_missing"]
        self.assertEqual(details, ["a", "b"])

    def test_replay_independent_root_determinism(self):
        left = load(HISTORY_PATH, "replay_history_root_a")
        right = load(HISTORY_PATH, "replay_history_root_b")
        self.assertIsNot(left, right)
        states = [(T1, {"A": "closed"})]
        snaps, ledger, head, count = chain(states)
        copied = {key: bytes(value) for key, value in snaps.items()}
        kwargs = dict(subject="worker", expected_head_sha256=head, min_seq=count)
        one = left.assess(snaps, ledger, {"A": "open"}, T3, [], OWNERS, ["owner"], **kwargs)
        two = right.assess(copied, bytes(ledger), {"A": "open"}, T3, [], {"owner": ["主人"], "worker": ["执行者"]},
                           ["owner"], **kwargs)
        self.assertEqual(one, two)
        self.assertEqual(parsed(one)["result"], "REGRESSION")
        map_a = load(CAP / "map_coverage.py", "replay_map_root_a")
        map_b = load(CAP / "map_coverage.py", "replay_map_root_b")
        self.assertIsNot(map_a, map_b)
        document = {"schema_version": "loop-map/v1", "author": "生产方", "verifier": "验收方", "steps": [
            {"id": "s1", "command": ["python3", "-m", "unittest"], "expected": "exit 0",
             "measured_source": "stdout sha256 " + OLD}]}
        raw_map = encode(document)
        digest = hashlib.sha256(raw_map).hexdigest()
        raw_receipt = encode({"schema_version": "loop-map-receipt/v1", "map_sha256": digest, "steps": [{"id": "s1"}]})
        left_map = map_a.assess_map(raw_map, raw_receipt, digest, None)
        right_map = map_b.assess_map(bytes(raw_map), bytes(raw_receipt), digest, None)
        self.assertEqual(left_map, right_map)
        self.assertEqual(parsed(left_map)["result"], "NO_REGRESSION")

    def test_replay_exit_codes_zero_is_not_closed(self):
        code, raw = ratchet({}, b"", {"A": "open"}, T3)
        self.assertEqual((code, parsed((code, raw))["result"], parsed((code, raw))["loops"]["A"]),
                         (0, "NO_REGRESSION", "open"))
        self.assertNotIn("CLOSED", parsed((code, raw))["result"])
        snaps, ledger, _, _ = chain([(T1, {"A": "closed"})])
        code, raw = ratchet(snaps, ledger, {"A": "open"}, T3)
        self.assertEqual((code, parsed((code, raw))["result"]), (1, "REGRESSION"))
        waiver = {"loop": "A", "reason": "pending review", "approved_by": "主人", "ts": T2}
        code, raw = ratchet(snaps, ledger, {}, T3, waivers=[waiver])
        self.assertEqual((code, parsed((code, raw))["result"]), (3, "WAIVED_PENDING"))
        self.assertNotEqual(code, 0)
        code, raw = ratchet({}, b"", {"A": "open"}, "not-a-timestamp")
        self.assertEqual((code, parsed((code, raw))["result"]), (5, "INPUT_ERROR"))
        code, raw = history.assess({}, b"", {}, T3, [], None, ["owner"], subject="worker",
                                   expected_head_sha256=history.ZERO, min_seq=0)
        self.assertEqual(code, 5)
        self.assertNotEqual(code, 1)
        self.assertEqual(parsed((code, raw))["result"], "INPUT_ERROR")


if __name__ == "__main__":
    unittest.main()
