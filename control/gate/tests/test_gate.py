import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "gate.py"
spec = importlib.util.spec_from_file_location("gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

V1 = {"model": "m1", "skill": "s1", "policy": "p1", "standard": "TRUST-REVIEW-1.0"}
CONFIG = {
    "schema_version": "gate-config/v1",
    "ledger_kind": "test",
    "trusted_adapters": ["fixture-adapter"],
    "identities": {"bot.worker": ["执行者", "Worker"], "bot.trainer": ["训练者"],
                   "bot.other": [], "human.owner": ["主人"]},
    "owner_identities": ["human.owner"],
    "units": [{"bot_id": "bot.worker", "capability_scope": "status-summary",
               "versions": V1, "producer": "bot.worker",
               "allowed_verifiers": ["bot.trainer"]}],
}
UNIT = "bot.worker::status-summary"
ALL_TRUE = {k: True for k in gate.CHECKS}


def auth(sender="bot.trainer", adapter="fixture-adapter"):
    return {"adapter": adapter, "sender": sender, "evidence_ref": f"fixture://{sender}"}


class Log:
    """Builds a sealed fixture log; every helper call appends one event."""

    def __init__(self):
        self.events, self.n = [], 0

    def result(self, task, verdict="PASS", receipt=None, **over):
        self.n += 1
        ev = {"schema_version": "gate-event/v1", "ts": f"2026-11-02T00:00:{self.n:02d}Z",
              "ledger_kind": "test", "event_id": f"e{self.n}", "kind": "result",
              "bot_id": "bot.worker", "capability_scope": "status-summary",
              "auth": auth(), "task_id": task, "task_revision": 1,
              "producer_message_id": f"pm{self.n}", "verification_message_id": f"vm{self.n}",
              "producer": "bot.worker", "versions": dict(V1), "status": "FINAL",
              "outer_verdict": verdict, "receipt_verdict": receipt or verdict,
              "checks": dict(ALL_TRUE), "real_business_run": False,
              "artifact_manifest_sha256": "a" * 64, "independent_rerun_ref": f"rerun://{task}"}
        ev.update(over)
        self.events.append(ev)
        return ev

    def control(self, action, sender="human.owner", **over):
        self.n += 1
        ev = {"schema_version": "gate-event/v1", "ts": f"2026-11-02T00:00:{self.n:02d}Z",
              "ledger_kind": "test", "event_id": f"e{self.n}", "kind": "control",
              "bot_id": "bot.worker", "capability_scope": "status-summary",
              "auth": auth(sender), "action": action, "versions": None,
              "reason": f"{action} fixture", "approval_ref": None}
        ev.update(over)
        self.events.append(ev)
        return ev

    def raw(self):
        draft = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.events)
        return gate.seal(draft.encode())


def cfg_raw(**over):
    c = copy.deepcopy(CONFIG)
    c.update(over)
    return json.dumps(c, ensure_ascii=False).encode()


def state_of(log, config=None):
    return json.loads(gate.replay(config or cfg_raw(), log.raw()))


def unit(log, config=None):
    s = state_of(log, config)
    return s["units"][UNIT], [d["effect"] for d in s["decisions"]], s


class StreakRules(unittest.TestCase):
    def three_distinct(self, log, real_on=1):
        for i in range(1, 4):
            log.result(f"t{i}", real_business_run=(i == real_on))

    def test_three_distinct_qualified_tasks_with_real_run_is_stage2_candidate(self):
        log = Log()
        self.three_distinct(log)
        u, effects, _ = unit(log)
        self.assertEqual(effects, ["COUNTED"] * 3)
        self.assertEqual((u["streak"], u["evidence_stage_candidate"], u["effective_stage"]), (3, 2, None))

    def test_two_tasks_or_no_real_run_is_not_candidate(self):
        log = Log()
        log.result("t1", real_business_run=True)
        log.result("t2")
        self.assertIsNone(unit(log)[0]["evidence_stage_candidate"])
        log = Log()
        self.three_distinct(log, real_on=None)
        u = unit(log)[0]
        self.assertEqual(u["streak"], 3)
        self.assertIsNone(u["evidence_stage_candidate"])

    def test_ceiling_is_two_even_after_many_passes(self):
        log = Log()
        for i in range(10):
            log.result(f"t{i}", real_business_run=True)
        u = unit(log)[0]
        self.assertEqual((u["streak"], u["evidence_stage_candidate"], u["effective_stage"]), (10, 2, None))

    def test_same_task_counts_once_and_does_not_reset(self):
        log = Log()
        log.result("t1")
        log.result("t1", task_revision=2)
        log.result("t2")
        u, effects, _ = unit(log)
        self.assertEqual(effects, ["COUNTED", "NOOP_DUP_TASK", "COUNTED"])
        self.assertEqual(u["streak"], 2)

    def test_replayed_event_and_reused_message_are_noop(self):
        log = Log()
        first = log.result("t1")
        log.n += 1
        log.events.append(dict(first, ts="2026-11-02T00:00:02Z"))  # same event_id replayed
        log.result("t2", verification_message_id=first["verification_message_id"])
        u, effects, s = unit(log)
        self.assertEqual(effects, ["COUNTED", "NOOP_REPLAY", "NOOP_REPLAY"])
        self.assertEqual(u["streak"], 1)
        self.assertIn("vm1", s["consumed_message_ids"])

    def test_replayed_event_id_with_fresh_messages_is_noop(self):
        log = Log()
        first = log.result("t1")
        log.result("t2", event_id=first["event_id"])
        u, effects, _ = unit(log)
        self.assertEqual((effects, u["streak"]), (["COUNTED", "NOOP_REPLAY"], 1))

    def test_fail_resets_and_new_revision_counts_fresh(self):
        log = Log()
        log.result("t1")
        log.result("t2", verdict="FAIL")
        log.result("t2", task_revision=2)
        u, effects, _ = unit(log)
        self.assertEqual(effects, ["COUNTED", "RESET", "COUNTED"])
        self.assertEqual(u["window"], [{"task_id": "t2", "real_business_run": False}])

    def test_hold_neither_adds_nor_subtracts_and_keeps_message_available(self):
        log = Log()
        log.result("t1")
        held = log.result("t2", status="HOLD", outer_verdict=None, receipt_verdict=None)
        log.result("t2", producer_message_id=held["producer_message_id"],
                   verification_message_id=held["verification_message_id"])
        u, effects, _ = unit(log)
        self.assertEqual(effects, ["COUNTED", "NOOP_HOLD", "COUNTED"])
        self.assertEqual(u["streak"], 2)

    def test_unknown_unit_rejected_without_side_effect(self):
        log = Log()
        log.result("t1", bot_id="bot.other")
        u, effects, _ = unit(log)
        self.assertEqual((effects, u["streak"]), (["REJECTED"], 0))


class PrototypeCounterexamples(unittest.TestCase):
    """The four blocking defects from 07-实测案例与反例索引 must stay red."""

    def test_body_author_role_cannot_stand_in_for_sender(self):
        log = Log()
        log.result("t1")
        log.result("t2", auth=None, body={"author_role": "训练者", "approved_by": "主人"})
        u, effects, s = unit(log)
        self.assertEqual(effects, ["COUNTED", "RESET"])
        self.assertIn("not authenticated", s["decisions"][1]["reason"])
        self.assertEqual(u["streak"], 0)

    def test_untrusted_adapter_or_empty_evidence_ref_is_not_authentication(self):
        for bad in (auth(adapter="self-reported"), dict(auth(), evidence_ref="  ")):
            log = Log()
            log.result("t1", auth=bad)
            self.assertEqual(unit(log)[1], ["RESET"])

    def test_outer_pass_inner_fail_freezes_and_keeps_streak(self):
        log = Log()
        log.result("t1", real_business_run=True)
        log.result("t2")
        log.result("t3", verdict="PASS", receipt="FAIL")
        log.result("t4")
        u, effects, _ = unit(log)
        self.assertEqual(effects, ["COUNTED", "COUNTED", "CONFLICT_FROZEN", "PAUSED_FROZEN"])
        self.assertEqual((u["streak"], u["frozen"], u["evidence_stage_candidate"]), (2, True, None))

    def test_pass_with_failed_inner_check_is_conflict(self):
        log = Log()
        log.result("t1", checks=dict(ALL_TRUE, challenge=False))
        u, effects, _ = unit(log)
        self.assertEqual((effects, u["frozen"]), (["CONFLICT_FROZEN"], True))

    def test_streak_cannot_bridge_missing_evidence(self):
        log = Log()
        log.result("t1", real_business_run=True)
        log.result("t2")
        log.result("t3", verdict="NOT_TESTED")
        log.result("t4")
        u, effects, _ = unit(log)
        self.assertEqual(effects, ["COUNTED", "COUNTED", "RESET", "COUNTED"])
        self.assertEqual((u["streak"], u["evidence_stage_candidate"]), (1, None))

    def test_pass_with_missing_evidence_is_not_counted(self):
        for over in ({"checks": dict(ALL_TRUE, evidence=None)},
                     {"independent_rerun_ref": None}, {"artifact_manifest_sha256": None}):
            log = Log()
            log.result("t1")
            log.result("t2", **over)
            u, effects, _ = unit(log)
            self.assertEqual((effects, u["streak"]), (["COUNTED", "RESET"], 0), over)

    def test_empty_assertion_self_test_via_alias_is_blocked(self):
        log = Log()
        log.result("t1", auth=auth("Worker"), independent_rerun_ref=None)
        _, effects, s = unit(log)
        self.assertEqual(effects, ["RESET"])
        self.assertIn("self-verification", s["decisions"][0]["reason"])


class IdentityRules(unittest.TestCase):
    def test_alias_normalizes_case_insensitively(self):
        log = Log()
        log.result("t1", auth=auth("训练者"), producer="WORKER")
        self.assertEqual(unit(log)[1], ["COUNTED"])

    def test_verifier_not_on_capability_allowlist(self):
        log = Log()
        log.result("t1", auth=auth("bot.other"))
        self.assertEqual(unit(log)[1], ["RESET"])

    def test_unknown_sender_or_producer_or_wrong_producer(self):
        for over in ({"auth": auth("stranger")}, {"producer": "stranger"},
                     {"producer": "bot.other"}):
            log = Log()
            log.result("t1", **over)
            self.assertEqual(unit(log)[1], ["RESET"], over)

    def test_same_message_as_production_and_verification(self):
        log = Log()
        log.result("t1", verification_message_id="pm1")
        self.assertEqual(unit(log)[1], ["RESET"])


class VersionAndFreeze(unittest.TestCase):
    def test_version_drift_event_is_rejected_without_counting(self):
        log = Log()
        log.result("t1")
        log.result("t2", versions=dict(V1, model="m0"))
        u, effects, _ = unit(log)
        self.assertEqual((effects, u["streak"]), (["COUNTED", "REJECTED"], 1))

    def test_owner_version_change_invalidates_streak(self):
        log = Log()
        log.result("t1")
        log.result("t2")
        log.control("version_change", versions=dict(V1, skill="s2"))
        log.result("t3", versions=dict(V1, skill="s2"))
        log.result("t4")  # old version now drifts
        u, effects, _ = unit(log)
        self.assertEqual(effects, ["COUNTED", "COUNTED", "CONTROL_APPLIED", "COUNTED", "REJECTED"])
        self.assertEqual((u["streak"], u["versions"]["skill"]), (1, "s2"))
        self.assertEqual(u["counted_task_ids"], ["t1", "t2", "t3"])

    def test_control_needs_authenticated_owner(self):
        for sender, a in (("bot.worker", None), ("bot.trainer", None), ("human.owner", "x")):
            log = Log()
            ev = log.control("freeze", sender=sender)
            if a == "x":
                ev["auth"] = None
            log.result("t1")
            u, effects, _ = unit(log)
            self.assertEqual(effects, ["REJECTED", "COUNTED"], sender)
            self.assertFalse(u["frozen"])
        log = Log()
        log.control("version_change", versions=dict(V1))
        self.assertEqual(unit(log)[1], ["REJECTED"])

    def test_unfreeze_requires_approval_and_preserves_streak(self):
        log = Log()
        log.result("t1", real_business_run=True)
        log.result("t2", verdict="PASS", receipt="CONFLICT")
        log.control("unfreeze")
        log.control("unfreeze", approval_ref="approval://owner/1")
        log.result("t3")
        log.result("t4")
        u, effects, _ = unit(log)
        self.assertEqual(effects, ["COUNTED", "CONFLICT_FROZEN", "REJECTED", "CONTROL_APPLIED",
                                   "COUNTED", "COUNTED"])
        self.assertEqual((u["streak"], u["frozen"], u["evidence_stage_candidate"]), (3, False, 2))

    def test_freeze_after_three_passes_withdraws_candidate(self):
        log = Log()
        for i in range(1, 4):
            log.result(f"t{i}", real_business_run=True)
        log.control("freeze")
        u = unit(log)[0]
        self.assertEqual((u["streak"], u["frozen"], u["evidence_stage_candidate"]), (3, True, None))

    def test_failure_while_frozen_still_resets(self):
        log = Log()
        log.result("t1")
        log.control("freeze")
        log.result("t2", verdict="FAIL")
        u, effects, _ = unit(log)
        self.assertEqual((effects[-1], u["streak"], u["frozen"]), ("RESET", 0, True))


class LogIntegrity(unittest.TestCase):
    def base(self):
        log = Log()
        for i in range(1, 4):
            log.result(f"t{i}")
        return log.raw()

    def assertInputError(self, raw, config=None):
        with self.assertRaises(gate.InputError):
            gate.replay(config or cfg_raw(), raw)

    def test_tampered_byte_breaks_chain(self):
        raw = self.base()
        lines = raw.split(b"\n")
        lines[1] = lines[1].replace(b'"t2"', b'"t9"')
        self.assertInputError(b"\n".join(lines))

    def test_deleted_or_reordered_history(self):
        lines = self.base().split(b"\n")[:-1]
        self.assertInputError(lines[0] + b"\n" + lines[2] + b"\n")
        self.assertInputError(lines[1] + b"\n" + lines[0] + b"\n" + lines[2] + b"\n")

    def test_seq_gap_with_valid_chain_is_rejected(self):
        log = Log()
        log.result("t1")
        draft = json.dumps(log.events[0]).encode() + b"\n"
        self.assertInputError(gate.seal(draft, start_seq=2))

    def test_truncated_or_padded_log(self):
        raw = self.base()
        self.assertInputError(raw[:-1])
        self.assertInputError(raw + b"\n")
        self.assertInputError(b" " + raw)

    def test_time_must_not_go_backwards(self):
        log = Log()
        log.result("t1", ts="2026-11-02T00:00:09Z")
        log.result("t2", ts="2026-11-02T00:00:08Z")
        self.assertInputError(log.raw())
        log = Log()
        log.result("t1", ts="2026-02-30T00:00:00Z")
        self.assertInputError(log.raw())

    def test_test_events_never_enter_real_ledger(self):
        self.assertInputError(self.base(), cfg_raw(ledger_kind="real"))

    def test_schema_violations_are_input_errors(self):
        bad = [{"surprise": 1}, {"status": "DONE"}, {"outer_verdict": "pass"},
               {"checks": {"sources": True}}, {"real_business_run": 1},
               {"artifact_manifest_sha256": "A" * 64}, {"task_revision": True},
               {"auth": {"adapter": "fixture-adapter", "sender": "bot.trainer"}},
               {"schema_version": "gate-event/v2"}]
        for over in bad:
            log = Log()
            log.result("t1", **over)
            self.assertInputError(log.raw())
        dup = self.base().split(b"\n")[0].replace(b'{"', b'{"seq":1,"', 1) + b"\n"
        self.assertInputError(dup)

    def test_config_errors(self):
        ids = copy.deepcopy(CONFIG["identities"])
        ids["bot.other"] = ["worker"]  # collides with bot.worker alias
        self.assertInputError(self.base(), cfg_raw(identities=ids))
        units = copy.deepcopy(CONFIG["units"])
        units[0]["allowed_verifiers"].append("执行者")
        self.assertInputError(self.base(), cfg_raw(units=units))
        units = copy.deepcopy(CONFIG["units"])
        units[0]["allowed_verifiers"] = ["nobody"]
        self.assertInputError(self.base(), cfg_raw(units=units))

    def test_empty_log_and_default_no_trusted_adapter(self):
        s = json.loads(gate.replay(cfg_raw(), b""))
        self.assertEqual((s["last_seq"], s["units"][UNIT]["streak"]), (0, 0))
        log = Log()
        for i in range(3):
            log.result(f"t{i}", real_business_run=True)
        u, effects, _ = unit(log, cfg_raw(trusted_adapters=[]))
        self.assertEqual((effects, u["streak"]), (["RESET"] * 3, 0))

    def test_replay_is_deterministic(self):
        raw = self.base()
        self.assertEqual(gate.replay(cfg_raw(), raw), gate.replay(cfg_raw(), raw))


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        log = Log()
        for i in range(1, 4):
            log.result(f"t{i}", real_business_run=(i == 2))
        (self.dir / "config.json").write_bytes(cfg_raw())
        (self.dir / "events.jsonl").write_bytes(log.raw())

    def run_cli(self, *args):
        p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, timeout=20)
        return p.returncode, p.stdout

    def common(self):
        return ["--config", str(self.dir / "config.json"), "--events", str(self.dir / "events.jsonl")]

    def test_replay_then_verify_match_and_regression(self):
        code, out = self.run_cli("replay", *self.common())
        self.assertEqual(code, 0)
        ledger = self.dir / "ledger.json"
        ledger.write_bytes(out)
        self.assertEqual(self.run_cli("verify", *self.common(), "--ledger", str(ledger))[0], 0)
        tampered = json.loads(out)
        tampered["units"][UNIT]["streak"] = 4
        ledger.write_bytes(gate.canonical(tampered))
        code, out = self.run_cli("verify", *self.common(), "--ledger", str(ledger))
        self.assertEqual((code, json.loads(out)["result"]), (1, "REGRESSION"))

    def test_corrupt_input_is_exit5_not_regression(self):
        (self.dir / "events.jsonl").write_bytes(b"{not json}\n")
        code, out = self.run_cli("verify", *self.common(), "--ledger", str(self.dir / "missing"))
        self.assertEqual((code, json.loads(out)["result"]), (5, "INPUT_ERROR"))
        code, _ = self.run_cli("replay", "--config", str(self.dir / "nope.json"),
                               "--events", str(self.dir / "events.jsonl"))
        self.assertEqual(code, 5)

    def test_usage_error_is_argparse_exit2(self):
        self.assertEqual(self.run_cli()[0], 2)


if __name__ == "__main__":
    unittest.main()
