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


def assess(snapshots, ledger, current, ts, waivers, aliases, owners, **controls):
    # Test caller simulates a trusted checkpoint. Attack tests supply the retained
    # pre-attack checkpoint explicitly, never derive it from the tampered input.
    lines = ledger.splitlines()
    defaults = {"subject": "worker", "min_seq": len(lines),
                "expected_head_sha256": hashlib.sha256(lines[-1]).hexdigest() if lines else h.ZERO}
    defaults.update(controls)
    return h.assess(snapshots, ledger, current, ts, waivers, aliases, owners, **defaults)


T1 = "2026-11-02T09:00+08:00"
T2 = "2026-11-02T10:00+08:00"
T3 = "2026-11-02T11:00+08:00"


class Ratchet(unittest.TestCase):
    def run_case(self, states, current, ts=T3, waivers=None):
        snaps, ledger = history(states)
        return assess(snaps, ledger, current, ts, waivers or [], OWNERS, ["owner"])

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
        x = assess(*a, {"A": "open"}, T3, [], OWNERS, ["owner"])
        y = assess(*b, {"A": "open"}, T3, [], copy.deepcopy(OWNERS), ["owner"])
        self.assertEqual(x, y)


class Integrity(unittest.TestCase):
    def setUp(self):
        self.snapshots, self.ledger = history([(T1, {"A": "closed"}), (T2, {"A": "open"})])

    def call(self, snapshots=None, ledger=None):
        return assess(self.snapshots if snapshots is None else snapshots,
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
            self.assertEqual(assess(s, ledger, {}, T3, [], OWNERS, ["owner"])[0], 5)
            self.assertEqual(assess({}, b"", {}, ts, [], OWNERS, ["owner"])[0], 5)

    def test_bad_json_unknown_states_and_alias_collision(self):
        self.assertEqual(self.call(ledger=b"not json\n"), 5)
        for states in ({"A": "pass"}, {"A": True}, {"": "closed"}):
            self.assertEqual(assess({}, b"", states, T3, [], OWNERS, ["owner"])[0], 5)
        self.assertEqual(assess({}, b"", {}, T3, [], {"a": ["X"], "b": ["x"]}, ["a"])[0], 5)

    def test_unexpected_failure_is_5_not_regression_1(self):
        self.assertEqual(assess({}, b"", {}, T3, [], None, ["owner"])[0], 5)


class ReviewF1F4(unittest.TestCase):
    def setUp(self):
        self.snaps, self.ledger = history([(T1, {"A": "closed"}), (T2, {"A": "open"})])
        self.head = hashlib.sha256(self.ledger.splitlines()[-1]).hexdigest()

    def test_cleared_or_truncated_history_rejects_retained_checkpoint(self):
        shortened, ledger = history([(T1, {"A": "closed"})])
        for snaps, raw in (({}, b""), (shortened, ledger)):
            self.assertEqual(assess(snaps, raw, {}, T3, [], OWNERS, ["owner"],
                                   expected_head_sha256=self.head, min_seq=2)[0], 5)

    def test_rewritten_whole_history_rejects_same_length_checkpoint(self):
        snaps, raw = history([(T1, {"A": "open"}), (T2, {"A": "open"})])
        self.assertEqual(assess(snaps, raw, {}, T3, [], OWNERS, ["owner"],
                               expected_head_sha256=self.head, min_seq=2)[0], 5)

    def test_checkpoint_and_subject_are_mandatory(self):
        self.assertEqual(h.assess({}, b"", {}, T3, [], OWNERS, ["owner"])[0], 5)
        for control in ({"min_seq": True}, {"min_seq": -1}, {"expected_head_sha256": "bad"},
                        {"subject": "unknown"}):
            self.assertEqual(assess({}, b"", {}, T3, [], OWNERS, ["owner"], **control)[0], 5)

    def test_minimum_sequence_is_checked_separately(self):
        self.assertEqual(assess(self.snaps, self.ledger, {}, T3, [], OWNERS, ["owner"], min_seq=3)[0], 5)

    def test_stale_equal_future_and_fresh_waivers(self):
        w = {"loop": "A", "reason": "pending", "approved_by": "主人", "ts": T3}
        for ts in ("2020-01-01T00:00+08:00", T1, T2,
                   "2026-11-02T02:00+00:00", "2026-11-02T12:00+08:00"):
            self.assertEqual(assess(self.snaps, self.ledger, {}, T3, [dict(w, ts=ts)], OWNERS, ["owner"])[0], 5)
        self.assertEqual(assess(self.snaps, self.ledger, {}, T3, [w], OWNERS, ["owner"])[0], 3)

    def test_waiver_cannot_be_reused_after_next_snapshot(self):
        w = {"loop": "A", "reason": "pending", "approved_by": "owner", "ts": T2}
        snaps, raw = history([(T1, {"A": "closed"})])
        self.assertEqual(assess(snaps, raw, {}, T3, [w], OWNERS, ["owner"])[0], 3)
        self.assertEqual(assess(self.snaps, self.ledger, {}, T3, [w], OWNERS, ["owner"])[0], 5)

    def test_self_owner_by_canonical_or_alias_is_invalid(self):
        for owner in ("worker", "执行者"):
            self.assertEqual(assess({}, b"", {}, T3, [], OWNERS, [owner])[0], 5)
        self.assertEqual(assess({}, b"", {}, T3, [], OWNERS, ["worker"], subject="执行者")[0], 5)

    def test_fullwidth_self_owner_is_rejected(self):
        fullwidth_worker = "\uff57orker"
        for owners, subject in (([fullwidth_worker], "worker"), (["worker"], fullwidth_worker),
                                ([fullwidth_worker], "执行者")):
            code, raw = assess({}, b"", {"A": "open"}, T3, [], OWNERS, owners, subject=subject)
            self.assertEqual(code, 5, (owners, subject))
            self.assertIn("own waiver", json.loads(raw)["reason"])
        collided = {"worker": ["执行者"], "\uff57orker": ["other"]}
        self.assertEqual(assess({}, b"", {}, T3, [], collided, ["执行者"], subject="other")[0], 5)

    def test_embedded_zero_width_self_owner_is_rejected(self):
        for owners, subject in ((["wor\u200bker"], "worker"), (["worker\u200b"], "worker"),
                                (["\u200bworker"], "执行者"), (["执行者"], "wor\u200bker")):
            code, raw = assess({}, b"", {"A": "open"}, T3, [], OWNERS, owners, subject=subject)
            self.assertEqual(code, 5, (owners, subject))
            self.assertIn("own waiver", json.loads(raw)["reason"])

    def test_zero_width_only_is_not_an_identity(self):
        for owners, subject in ((["\u200b"], "worker"), (["\ufeff"], "worker"), (["主人"], "\u200b")):
            code, raw = assess({}, b"", {"A": "open"}, T3, [], OWNERS, owners, subject=subject)
            self.assertEqual(code, 5, (owners, subject))
            self.assertEqual(json.loads(raw)["result"], "INPUT_ERROR")
            self.assertNotIn("own waiver", json.loads(raw)["reason"])
        bad = {"owner": ["主人"], "worker": ["\u200b"]}
        code, raw = assess({}, b"", {"A": "open"}, T3, [], bad, ["主人"], subject="worker")
        self.assertEqual(code, 5)
        self.assertIn("invalid alias", json.loads(raw)["reason"])

    def test_internal_whitespace_is_input_error_for_owner_subject_and_approver(self):
        spaced = ("wor ker", "wor\u3000ker", "wor\u00a0ker", "wor\tker")
        for bad in spaced:
            for owners, subject in (([bad], "worker"), (["主人"], bad)):
                code, raw = assess({}, b"", {"A": "open"}, T3, [], OWNERS, owners, subject=subject)
                body = json.loads(raw)
                self.assertEqual((code, body["result"]), (5, "INPUT_ERROR"), (owners, subject))
                self.assertIn("internal whitespace", body["reason"])
                self.assertNotIn(body["result"], ("NO_REGRESSION", "REGRESSION", "WAIVED_PENDING"))
        snaps, ledger = history([(T1, {"A": "closed"})])
        for bad in spaced:
            waiver = {"loop": "A", "reason": "pending", "approved_by": bad, "ts": T2}
            code, raw = assess(snaps, ledger, {}, T3, [waiver], OWNERS, ["主人"])
            body = json.loads(raw)
            self.assertEqual((code, body["result"]), (5, "INPUT_ERROR"), bad)
            self.assertIn("internal whitespace", body["reason"])
        aliased = {"owner": ["主人"], "worker": ["wor ker"]}
        code, raw = assess({}, b"", {"A": "open"}, T3, [], aliased, ["主人"], subject="worker")
        self.assertEqual(code, 5)
        self.assertIn("internal whitespace", json.loads(raw)["reason"])
        # Leading and trailing whitespace still strip, including U+3000 and NBSP.
        for owners, subject in ((["  主人  "], "worker"), (["主人"], "\u3000worker"),
                                (["主人"], "worker\u00a0"), (["\t主人"], "  worker  ")):
            code, raw = assess({}, b"", {"A": "open"}, T3, [], OWNERS, owners, subject=subject)
            self.assertEqual((code, json.loads(raw)["result"]), (0, "NO_REGRESSION"), (owners, subject))

    def test_distinct_name_is_not_treated_as_self(self):
        for owners, subject in ((["主人"], "worker"), (["主人\u200b"], "worker"),
                                (["\uff4fwner"], "worker"), (["\uff4fwner"], "执行者\u200b")):
            code, raw = assess({}, b"", {"A": "open"}, T3, [], OWNERS, owners, subject=subject)
            self.assertEqual((code, json.loads(raw)["result"]), (0, "NO_REGRESSION"), (owners, subject))
        snaps, ledger = history([(T1, {"A": "closed"})])
        waiver = {"loop": "A", "reason": "pending", "approved_by": "\uff4fwner", "ts": T2}
        code, raw = assess(snaps, ledger, {}, T3, [waiver], OWNERS, ["主人"])
        self.assertEqual((code, json.loads(raw)["result"]), (3, "WAIVED_PENDING"))
        disguised = dict(waiver, approved_by="wor\u200bker")
        self.assertEqual(assess(snaps, ledger, {}, T3, [disguised], OWNERS, ["主人"])[0], 5)

    def test_name_fold_matches_loop_closure(self):
        spec = importlib.util.spec_from_file_location(
            "loop_closure_detect", ROOT.parents[1] / "capabilities" / "loop_closure" / "detect.py")
        detect = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(detect)
        for name in ("Worker", "\uff57orker", "wor\u200bker", "\u200b", "\ufeff", "  ", "主人",
                     "执行者\u200b", "  worker  ", "\u3000worker", "worker\u00a0"):
            self.assertEqual(h.normalize_name(name), detect.normalize_name(name), name)
        for name in ("wor ker", "wor\u3000ker", "wor\u00a0ker", "wor\tker", "wo\u2003rker"):
            with self.assertRaises(h.InputError):
                h.normalize_name(name)
            with self.assertRaises(detect.InputError):
                detect.normalize_name(name)

    def test_only_lf_ledger_is_accepted(self):
        for raw in (self.ledger.replace(b"\n", b"\r\n"), self.ledger.replace(b"\n", b"\r")):
            self.assertEqual(assess(self.snaps, raw, {}, T3, [], OWNERS, ["owner"],
                                   expected_head_sha256=self.head, min_seq=2)[0], 5)
        self.assertEqual(assess(self.snaps, self.ledger, {}, T3, [], OWNERS, ["owner"])[0], 1)


LIMIT = 16 * 1024 * 1024
SCOPE = "history integrity only; no closure authentication or stage changes"


def canonical_bytes(value):
    # Independent of history.canonical. Mutants of that function must not match this.
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def error_bytes(reason):
    return canonical_bytes({"reason": reason, "result": "INPUT_ERROR"})


def chain(rows):
    snapshots, lines, previous = {}, [], "0" * 64
    for number, (sid, snap) in enumerate(rows, 1):
        snapshots[sid] = encode(snap)
        line = encode({"prev_sha256": previous, "seq": number, "sha256": hashlib.sha256(snapshots[sid]).hexdigest(),
                        "snapshot_id": sid}).rstrip(b"\n")
        previous = hashlib.sha256(line).hexdigest()
        lines.append(line + b"\n")
    return snapshots, b"".join(lines)


class Surface(unittest.TestCase):
    """Pin exit-code, reason, and canonical bytes of the frozen history.py contract."""

    def assert_error(self, reason, snapshots, ledger, current, ts, waivers, aliases, owners, **controls):
        code, raw = assess(snapshots, ledger, current, ts, waivers, aliases, owners, **controls)
        self.assertEqual(raw, error_bytes(reason))
        self.assertEqual(code, 5)

    def assert_direct(self, reason, func, *args):
        with self.assertRaises(h.InputError) as caught:
            func(*args)
        self.assertEqual(str(caught.exception), reason)

    def test_canonical_and_each_result_byte_for_byte(self):
        self.assertEqual(h.canonical({"b": 1, "a": "甲"}), canonical_bytes({"b": 1, "a": "甲"}))
        code, raw = assess({}, b"", {"甲": "open"}, T3, [], OWNERS, ["owner"])
        self.assertEqual(code, 0)
        self.assertEqual(raw, canonical_bytes({
            "baseline": [], "history_seq": 0, "last_history_sha256": "0" * 64,
            "loops": {"甲": "open"}, "regressions": [], "result": "NO_REGRESSION",
            "scope": SCOPE, "ts": T3, "waived_pending": [],
        }))
        snaps, ledger = history([(T1, {"A": "closed"})])
        code, raw = assess(snaps, ledger, {"A": "open"}, T3, [], OWNERS, ["owner"])
        self.assertEqual(code, 1)
        body = json.loads(raw)
        self.assertEqual(body["result"], "REGRESSION")
        self.assertEqual(body["regressions"], ["A"])
        self.assertEqual(raw, canonical_bytes(body))
        waiver = {"approved_by": "主人", "loop": "A", "reason": "pending", "ts": T2}
        code, raw = assess(snaps, ledger, {}, T3, [waiver], OWNERS, ["owner"])
        self.assertEqual(code, 3)
        body = json.loads(raw)
        self.assertEqual(body["result"], "WAIVED_PENDING")
        self.assertEqual(body["waived_pending"], ["A"])
        self.assertEqual(raw, canonical_bytes(body))

    def test_load_timestamp_and_size_boundaries(self):
        self.assert_direct("expected bounded raw bytes", h.load, None)
        self.assert_direct("expected bounded raw bytes", h.load, "abc")
        self.assert_direct("expected bounded raw bytes", h.load, b"x" * (LIMIT + 1))
        self.assert_direct("invalid JSON bytes", h.load, b"x" * LIMIT)
        self.assert_direct("invalid JSON bytes", h.load, b"{")
        self.assert_direct("duplicate JSON key", h.unique, [("a", 1), ("a", 2)])
        with self.assertRaises(h.InputError) as caught:
            h.load(b'{"a":1,"a":2}')
        self.assertEqual(str(caught.exception), "invalid JSON bytes")
        self.assert_direct("invalid timestamp format", h.timestamp, None)
        self.assert_direct("invalid timestamp format", h.timestamp, "nope")
        self.assert_direct("invalid calendar time or offset", h.timestamp, "2026-11-02T09:00+00:60")
        self.assert_direct("invalid calendar time or offset", h.timestamp, "2026-02-30T00:00+08:00")
        for ts in ("2026-11-02T09:00+23:00", "2026-11-02T09:00+00:59"):
            self.assertEqual(assess({}, b"", {}, ts, [], OWNERS, ["owner"])[0], 0, ts)
        huge = b"x" * (LIMIT + 1)
        self.assert_error("invalid history inputs", {}, huge, {}, T3, [], OWNERS, ["owner"])
        exact = b"\n" * LIMIT
        self.assert_error("blank or padded ledger line", {}, exact, {}, T3, [], OWNERS, ["owner"])

    def test_each_assess_error_names_its_reason(self):
        snaps, ledger = history([(T1, {"A": "closed"})])
        padded = ledger[:-1] + b" \n"
        array_line = b'["prev_sha256","seq","sha256","snapshot_id"]\n'
        bad_hex = "g" * 64
        wrong_hex = "ab" * 32
        snap_hash = hashlib.sha256(snaps["snapshot-1"]).hexdigest().encode()
        bad_digest = ledger.replace(snap_hash, bad_hex.encode(), 1)
        upper_id, upper_ledger = chain([("Snap1", {"loops": {"A": "closed"}, "ts": T1})])
        spaced, spaced_ledger = chain([("Bad Id", {"loops": {"A": "open"}, "ts": T1})])
        same, same_ledger = history([(T1, {"A": "closed"}), (T1, {"A": "open"})])
        changed = dict(snaps)
        changed["snapshot-1"] = snaps["snapshot-1"] + b" "
        extra = dict(snaps)
        extra["extra"] = b"{}\n"
        missing = dict(snaps)
        missing.pop("snapshot-1")
        snapshot_list = dict(snaps)
        snapshot_list["snapshot-1"] = b'["loops","ts"]\n'
        digest_ledger = ledger.replace(snap_hash, hashlib.sha256(snapshot_list["snapshot-1"]).hexdigest().encode(), 1)
        seq_row = json.loads(ledger.splitlines()[0])
        seq_row["seq"] = 9
        seq_ledger = encode(seq_row)
        id_row = json.loads(ledger.splitlines()[0])
        id_row["snapshot_id"] = 1
        id_ledger = encode(id_row)
        dup_rows = [json.loads(line) for line in same_ledger.splitlines()]
        dup_rows[1]["snapshot_id"] = dup_rows[0]["snapshot_id"]
        dup_ledger = b"".join(encode(row) for row in dup_rows)
        cases = [
            ("format", {}, b"", {}, "nope", [], OWNERS, ["owner"], {}, "invalid timestamp format"),
            ("calendar", {}, b"", {}, "2026-02-30T00:00+08:00", [], OWNERS, ["owner"], {}, "invalid calendar time or offset"),
            ("minute60", {}, b"", {}, "2026-11-02T09:00+00:60", [], OWNERS, ["owner"], {}, "invalid calendar time or offset"),
            ("loops", {}, b"", {"A": "pass"}, T3, [], OWNERS, ["owner"], {}, "invalid loop states"),
            ("empty-config", {}, b"", {}, T3, [], {}, ["owner"], {}, "invalid identity configuration"),
            ("config-type", {}, b"", {}, T3, [], ["owner"], ["owner"], {}, "invalid identity configuration"),
            ("identity", {}, b"", {}, T3, [], {"": []}, [""], {}, "invalid identity"),
            ("names-type", {}, b"", {}, T3, [], {"ok": "x"}, ["ok"], {}, "invalid identity"),
            ("alias", {}, b"", {}, T3, [], {"ok": [""]}, ["ok"], {}, "invalid alias"),
            ("ambiguous", {}, b"", {}, T3, [], {"a": ["X"], "b": ["x"]}, ["a"], {"subject": "a"}, "ambiguous alias"),
            ("owner", {}, b"", {}, T3, [], OWNERS, ["nobody"], {}, "unknown owner"),
            ("owner-type", {}, b"", {}, T3, [], OWNERS, [1], {}, "unknown owner"),
            ("subject", {}, b"", {}, T3, [], OWNERS, ["owner"], {"subject": "nobody"}, "unknown subject"),
            ("subject-type", {}, b"", {}, T3, [], OWNERS, ["owner"], {"subject": None}, "unknown subject"),
            ("self", {}, b"", {}, T3, [], OWNERS, ["worker"], {}, "subject cannot approve its own waiver"),
            ("history-type", [], b"", {}, T3, [], OWNERS, ["owner"], {}, "invalid history inputs"),
            ("truncated", {}, b"{", {}, T3, [], OWNERS, ["owner"], {}, "truncated ledger"),
            ("cr", {}, b"\r\n", {}, T3, [], OWNERS, ["owner"], {}, "ledger must use LF, not CR or CRLF"),
            ("blank", {}, b"\n", {}, T3, [], OWNERS, ["owner"], {}, "blank or padded ledger line"),
            ("padded", {}, padded, {}, T3, [], OWNERS, ["owner"], {}, "blank or padded ledger line"),
            ("fields", {}, b"{}\n", {}, T3, [], OWNERS, ["owner"], {}, "ledger fields mismatch"),
            ("fields-list", {}, array_line, {}, T3, [], OWNERS, ["owner"], {}, "ledger fields mismatch"),
            ("digest", {}, bad_digest, {}, T3, [], OWNERS, ["owner"], {}, "invalid snapshot digest"),
            ("seq", {}, seq_ledger, {}, T3, [], OWNERS, ["owner"], {}, "ledger sequence or chain broken"),
            ("sid-space", spaced, spaced_ledger, {}, T3, [], OWNERS, ["owner"], {}, "invalid or duplicate snapshot id"),
            ("sid-type", {}, id_ledger, {}, T3, [], OWNERS, ["owner"], {}, "invalid or duplicate snapshot id"),
            ("sid-dup", same, dup_ledger, {}, T3, [], OWNERS, ["owner"], {}, "invalid or duplicate snapshot id"),
            ("changed", changed, ledger, {}, T3, [], OWNERS, ["owner"], {}, "historical snapshot changed"),
            ("missing", missing, ledger, {}, T3, [], OWNERS, ["owner"], {}, "missing historical snapshot"),
            ("shape", snapshot_list, digest_ledger, {}, T3, [], OWNERS, ["owner"], {}, "snapshot fields mismatch"),
            ("equal-ts", same, same_ledger, {}, T3, [], OWNERS, ["owner"], {}, "historical timestamps not strictly increasing"),
            ("extra", extra, ledger, {}, T3, [], OWNERS, ["owner"], {}, "unregistered historical snapshot"),
            ("dup-waiver", snaps, ledger, {}, T3, [
                {"approved_by": "owner", "loop": "A", "reason": "pending", "ts": T2},
                {"approved_by": "owner", "loop": "A", "reason": "again", "ts": T2},
            ], OWNERS, ["owner"], {}, "duplicate waiver loop"),
            ("waiver-type", snaps, ledger, {}, T3, None, OWNERS, ["owner"], {}, "waivers must be a list"),
            ("waiver-fields", snaps, ledger, {}, T3, [["approved_by", "loop", "reason", "ts"]], OWNERS, ["owner"], {}, "waiver fields mismatch"),
            ("waiver-missing", snaps, ledger, {}, T3, [{"loop": "A"}], OWNERS, ["owner"], {}, "waiver fields mismatch"),
            ("waiver-empty", snaps, ledger, {}, T3, [{"approved_by": "owner", "loop": "A", "reason": "", "ts": T2}], OWNERS, ["owner"], {}, "empty waiver field"),
            ("waiver-who", snaps, ledger, {}, T3, [{"approved_by": "worker", "loop": "A", "reason": "pending", "ts": T2}], OWNERS, ["owner"], {}, "waiver owner is not allowed"),
            ("waiver-future", snaps, ledger, {}, T3, [{"approved_by": "owner", "loop": "A", "reason": "pending", "ts": "2030-01-01T00:00+00:00"}], OWNERS, ["owner"], {}, "waiver must be later than latest history and no later than now"),
            ("now", snaps, ledger, {}, T1, [], OWNERS, ["owner"], {}, "current timestamp must be later than all history"),
            ("checkpoint", snaps, ledger, {}, T3, [], OWNERS, ["owner"], {"expected_head_sha256": wrong_hex}, "history does not match trusted checkpoint"),
            ("bad-head", {}, b"", {}, T3, [], OWNERS, ["owner"], {"expected_head_sha256": "zz"}, "trusted history head and minimum sequence are required"),
            ("head-type", {}, b"", {}, T3, [], OWNERS, ["owner"], {"expected_head_sha256": None}, "trusted history head and minimum sequence are required"),
            ("min-seq", {}, b"", {}, T3, [], OWNERS, ["owner"], {"min_seq": -1}, "trusted history head and minimum sequence are required"),
        ]
        for name, snapshots, ledger_value, current, ts, waivers, aliases, owners, controls, reason in cases:
            with self.subTest(name=name, reason=reason):
                self.assert_error(reason, snapshots, ledger_value, current, ts, waivers, aliases, owners, **controls)
        code, raw = assess(upper_id, upper_ledger, {"A": "closed"}, T3, [], OWNERS, ["owner"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(raw)["result"], "NO_REGRESSION")
        code, raw = h.assess({}, b"", {}, T3, [], OWNERS, ["owner"], subject="worker")
        self.assertEqual(raw, error_bytes("trusted history head and minimum sequence are required"))
        self.assertEqual(code, 5)
        code, raw = h.assess({}, "nope", {}, T3, [], OWNERS, ["owner"],
                             subject="worker", min_seq=0, expected_head_sha256="0" * 64)
        self.assertEqual(raw, error_bytes("invalid history inputs"))
        self.assertEqual(code, 5)

    def test_hour_above_23_is_rejected_by_the_explicit_guard(self):
        # +24:00 and +25:00 are inside the TIME grammar. The original guard
        # raises ValueError("offset") before fromisoformat. A one-digit hour
        # slice or a bound of 24 lets fromisoformat raise a different ValueError;
        # that context is what timestamp() returns to callers.
        for ts in ("2026-11-02T09:00+24:00", "2026-11-02T09:00+25:00", "2026-11-02T09:00-24:00"):
            with self.subTest(ts=ts):
                with self.assertRaises(h.InputError) as caught:
                    h.timestamp(ts)
                self.assertEqual(str(caught.exception), "invalid calendar time or offset")
                self.assertIsInstance(caught.exception.__context__, ValueError)
                self.assertEqual(caught.exception.__context__.args, ("offset",))

    def test_pending_is_an_accepted_state(self):
        code, raw = assess({}, b"", {"A": "pending"}, T3, [], OWNERS, ["owner"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(raw)["loops"]["A"], "pending")


if __name__ == "__main__":
    unittest.main()
