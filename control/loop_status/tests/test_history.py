import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("history", ROOT / "history.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
OWNERS = {"owner": ["主人"], "worker": ["执行者"]}


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode()


def history(states):
    snapshots, lines, previous = {}, [], "0" * 64
    for i, (ts, loops) in enumerate(states, 1):
        sid = "snapshot-" + str(i)
        snapshots[sid] = encode({"ts": ts, "loops": loops})
        line = encode({"seq": i, "prev_sha256": previous, "snapshot_id": sid,
                       "sha256": hashlib.sha256(snapshots[sid]).hexdigest()}).rstrip(b"\n")
        previous = hashlib.sha256(line).hexdigest()
        lines.append(line + b"\n")
    return snapshots, b"".join(lines)


T1 = "2026-11-02T09:00+08:00"
T2 = "2026-11-02T10:00+08:00"
T3 = "2026-11-02T11:00+08:00"


class Ratchet(unittest.TestCase):
    def run_case(self, states, current, ts=T3, waivers=None):
        snaps, ledger = history(states)
        return h.assess(snaps, ledger, current, ts, waivers or [], OWNERS, ["owner"])

    def test_initial_open_is_no_regression_not_closed(self):
        code, raw = self.run_case([], {"A": "open"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(raw)["loops"]["A"], "open")

    def test_regression_is_reported_every_time_until_repaired(self):
        first = [(T1, {"A": "closed"})]
        self.assertEqual(self.run_case(first, {"A": "open"})[0], 1)
        second = first + [(T2, {"A": "open"})]
        code, raw = self.run_case(second, {"A": "open"})
        self.assertEqual((code, json.loads(raw)["regressions"]), (1, ["A"]))
        self.assertEqual(self.run_case(second, {"A": "closed"})[0], 0)

    def test_disappeared_key_and_all_regressions_are_reported(self):
        code, raw = self.run_case([(T1, {"A": "closed", "C": "closed"})], {"C": "blocked"})
        self.assertEqual((code, json.loads(raw)["regressions"]), (1, ["A", "C"]))

    def test_backdated_or_equal_timestamp_is_input_error(self):
        for ts in ("2020-01-01T00:00+08:00", T1, "2026-11-02T01:00+00:00"):
            self.assertEqual(self.run_case([(T1, {"A": "closed"})], {}, ts)[0], 5)

    def test_offsets_compare_instants_not_strings(self):
        # 01:30 UTC is later than 09:00 UTC+8, despite the smaller displayed hour.
        self.assertEqual(self.run_case([(T1, {"A": "closed"})], {"A": "closed"}, "2026-11-02T01:30+00:00")[0], 0)

    def test_waiver_never_turns_regression_green(self):
        w = {"loop": "A", "reason": "pending review", "approved_by": "主人", "ts": T2}
        code, raw = self.run_case([(T1, {"A": "closed"})], {}, waivers=[w])
        self.assertEqual((code, json.loads(raw)["result"]), (3, "WAIVED_PENDING"))

    def test_partial_waiver_still_regression(self):
        w = {"loop": "A", "reason": "pending", "approved_by": "owner", "ts": T2}
        self.assertEqual(self.run_case([(T1, {"A": "closed", "C": "closed"})], {}, waivers=[w])[0], 1)

    def test_bad_waivers_are_input_errors_even_without_regression(self):
        good = {"loop": "A", "reason": "pending", "approved_by": "owner", "ts": T2}
        for w in ({k: v for k, v in good.items() if k != "approved_by"},
                  dict(good, approved_by="执行者"), dict(good, reason=""),
                  dict(good, ts="2026-11-02T9:30+08:00"), dict(good, ts="2030-01-01T00:00+00:00")):
            self.assertEqual(self.run_case([], {}, waivers=[w])[0], 5)

    def test_deterministic_across_independent_input_copies(self):
        a = history([(T1, {"A": "closed"})])
        b = history([(T1, {"A": "closed"})])
        x = h.assess(*a, {"A": "open"}, T3, [], OWNERS, ["owner"])
        y = h.assess(*b, {"A": "open"}, T3, [], copy.deepcopy(OWNERS), ["owner"])
        self.assertEqual(x, y)


class Integrity(unittest.TestCase):
    def setUp(self):
        self.snapshots, self.ledger = history([(T1, {"A": "closed"}), (T2, {"A": "open"})])

    def call(self, snapshots=None, ledger=None):
        return h.assess(self.snapshots if snapshots is None else snapshots,
                        self.ledger if ledger is None else ledger, {}, T3, [], OWNERS, ["owner"])[0]

    def test_missing_modified_and_unregistered_snapshot(self):
        for kind in ("missing", "changed", "extra"):
            s = dict(self.snapshots)
            if kind == "missing": s.pop("snapshot-1")
            elif kind == "changed": s["snapshot-1"] += b" "
            else: s["unregistered"] = b"{}"
            self.assertEqual(self.call(snapshots=s), 5, kind)

    def test_deleted_or_reordered_ledger_line(self):
        lines = self.ledger.splitlines(keepends=True)
        for raw in (lines[1], lines[1] + lines[0], b"", self.ledger[:-1], self.ledger + b"\n"):
            self.assertEqual(self.call(ledger=raw), 5)

    def test_duplicate_id_and_seq_gap_in_rebuilt_chain(self):
        rows = [json.loads(line) for line in self.ledger.splitlines()]
        for field, value in (("snapshot_id", "snapshot-1"), ("seq", 3), ("sha256", None)):
            modified = copy.deepcopy(rows)
            modified[1][field] = value
            self.assertEqual(self.call(ledger=b"".join(encode(r) for r in modified)), 5)

    def test_bad_timestamp_every_source_uses_same_parser(self):
        for ts in ("../escaped", "2026-11-02T9:30+08:00", "2026-02-30T00:00+08:00", "2026-11-02T00:00Z", "2026-11-02T09:00+08:99"):
            s, ledger = history([(ts, {"A": "closed"})])
            self.assertEqual(h.assess(s, ledger, {}, T3, [], OWNERS, ["owner"])[0], 5)
            self.assertEqual(h.assess({}, b"", {}, ts, [], OWNERS, ["owner"])[0], 5)

    def test_bad_json_unknown_states_and_alias_collision(self):
        self.assertEqual(self.call(ledger=b"not json\n"), 5)
        for states in ({"A": "pass"}, {"A": True}, {"": "closed"}):
            self.assertEqual(h.assess({}, b"", states, T3, [], OWNERS, ["owner"])[0], 5)
        self.assertEqual(h.assess({}, b"", {}, T3, [], {"a": ["X"], "b": ["x"]}, ["a"])[0], 5)

    def test_unexpected_failure_is_5_not_regression_1(self):
        self.assertEqual(h.assess({}, b"", {}, T3, [], None, ["owner"])[0], 5)


if __name__ == "__main__":
    unittest.main()
