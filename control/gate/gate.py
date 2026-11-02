#!/usr/bin/env python3
"""Pure, replayable streak gate (C2/C5 candidate).

Folds a hash-chained, append-only event log into a deterministic state.
It never authenticates anyone itself (C4 adapter is out of scope), never
writes a real ledger, never applies a stage, and has no path above stage 2.
"""
import argparse
from datetime import datetime
import hashlib
import json
import re
import sys

STAGE_CEILING = 2
REQUIRED_DISTINCT_TASKS = 3
VERDICTS = ("PASS", "FAIL", "NOT_TESTED", "BLOCKED", "CONFLICT")
CHECKS = ("sources", "uncertainty", "boundary", "handoff", "evidence", "challenge")
VERSION_KEYS = ("model", "skill", "policy", "standard")
GENESIS = "0" * 64
HEX64 = re.compile(r"[0-9a-f]{64}")
TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
MAX_LOG_BYTES = 16 * 1024 * 1024

EVENT_COMMON = {"schema_version", "seq", "prev_sha256", "ts", "ledger_kind",
                "event_id", "kind", "bot_id", "capability_scope", "auth"}
RESULT_FIELDS = {"task_id", "task_revision", "producer_message_id",
                 "verification_message_id", "producer", "versions", "status",
                 "outer_verdict", "receipt_verdict", "checks", "real_business_run",
                 "artifact_manifest_sha256", "independent_rerun_ref"}
CONTROL_FIELDS = {"action", "versions", "reason", "approval_ref"}
OPTIONAL = {"body"}  # untrusted free data; the gate never reads it


class InputError(ValueError):
    """Corrupt/ill-formed config, log or history: exit 5, never a verdict."""


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InputError("duplicate JSON key")
        out[key] = value
    return out


def _loads(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, RecursionError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError(f"invalid JSON: {type(error).__name__}") from None


def _str(value, what):
    if not isinstance(value, str) or not value or value != value.strip():
        raise InputError(f"{what} must be a non-empty trimmed string")
    return value


def _versions(value):
    if not isinstance(value, dict) or set(value) != set(VERSION_KEYS):
        raise InputError("versions must have exactly model/skill/policy/standard")
    return {k: _str(value[k], f"versions.{k}") for k in VERSION_KEYS}


def unit_key(bot_id, scope):
    return f"{bot_id}::{scope}"


def load_config(raw):
    cfg = _loads(raw)
    keys = {"schema_version", "ledger_kind", "trusted_adapters", "identities",
            "owner_identities", "units"}
    if not isinstance(cfg, dict) or set(cfg) != keys:
        raise InputError("config fields mismatch")
    if cfg["schema_version"] != "gate-config/v1":
        raise InputError("unknown config schema")
    if cfg["ledger_kind"] not in ("test", "real"):
        raise InputError("ledger_kind must be test or real")
    if not isinstance(cfg["trusted_adapters"], list):
        raise InputError("trusted_adapters must be a list")
    adapters = {_str(a, "adapter") for a in cfg["trusted_adapters"]}
    if not isinstance(cfg["identities"], dict) or not cfg["identities"]:
        raise InputError("identities must be a non-empty object")
    alias = {}
    for stable, names in cfg["identities"].items():
        _str(stable, "identity")
        if not isinstance(names, list):
            raise InputError("identity aliases must be a list")
        for name in [stable] + names:
            _str(name, "alias")
            folded = name.casefold()
            if alias.get(folded, stable) != stable:
                raise InputError(f"ambiguous alias: {name}")
            alias[folded] = stable
    def known(name):
        stable = alias.get(_str(name, "identity").casefold())
        if stable is None:
            raise InputError(f"config references unknown identity {name}")
        return stable
    if not isinstance(cfg["owner_identities"], list):
        raise InputError("owner_identities must be a list")
    owners = {known(o) for o in cfg["owner_identities"]}
    if not isinstance(cfg["units"], list) or not cfg["units"]:
        raise InputError("units must be a non-empty list")
    units = {}
    for u in cfg["units"]:
        if not isinstance(u, dict) or set(u) != {"bot_id", "capability_scope", "versions",
                                                 "producer", "allowed_verifiers"}:
            raise InputError("unit fields mismatch")
        key = unit_key(_str(u["bot_id"], "bot_id"), _str(u["capability_scope"], "capability_scope"))
        if key in units:
            raise InputError("duplicate unit")
        producer = known(u["producer"])
        if not isinstance(u["allowed_verifiers"], list):
            raise InputError("allowed_verifiers must be a list")
        verifiers = {known(v) for v in u["allowed_verifiers"]}
        if producer in verifiers:
            raise InputError("producer cannot be an allowed verifier")
        units[key] = {"versions": _versions(u["versions"]), "producer": producer,
                      "verifiers": verifiers}
    return {"ledger_kind": cfg["ledger_kind"], "adapters": adapters, "alias": alias,
            "owners": owners, "units": units}


def _check_event(ev, cfg):
    if not isinstance(ev, dict):
        raise InputError("event must be an object")
    kind = ev.get("kind")
    extra = RESULT_FIELDS if kind == "result" else CONTROL_FIELDS if kind == "control" else None
    if extra is None:
        raise InputError("unknown event kind")
    allowed = EVENT_COMMON | extra | OPTIONAL
    if not EVENT_COMMON | extra <= set(ev) or not set(ev) <= allowed:
        raise InputError(f"event fields mismatch for kind {kind}")
    if ev["schema_version"] != "gate-event/v1":
        raise InputError("unknown event schema")
    if ev["ledger_kind"] != cfg["ledger_kind"]:
        raise InputError("ledger_kind mismatch: test and real events never mix")
    for f in ("event_id", "bot_id", "capability_scope"):
        _str(ev[f], f)
    auth = ev["auth"]
    if auth is not None and (not isinstance(auth, dict)
                             or set(auth) != {"adapter", "sender", "evidence_ref"}
                             or not all(isinstance(auth[k], str) for k in auth)):
        raise InputError("auth must be null or {adapter, sender, evidence_ref} strings")
    if kind == "result":
        for f in ("task_id", "producer_message_id", "verification_message_id", "producer"):
            _str(ev[f], f)
        if type(ev["task_revision"]) is not int or ev["task_revision"] < 1:
            raise InputError("task_revision must be a positive integer")
        _versions(ev["versions"])
        if ev["status"] not in ("FINAL", "HOLD"):
            raise InputError("status must be FINAL or HOLD")
        for f in ("outer_verdict", "receipt_verdict"):
            if ev[f] is not None and ev[f] not in VERDICTS:
                raise InputError(f"{f} not a final verdict")
        if ev["status"] == "FINAL" and (ev["outer_verdict"] is None or ev["receipt_verdict"] is None):
            raise InputError("FINAL event needs both verdicts")
        checks = ev["checks"]
        if not isinstance(checks, dict) or set(checks) != set(CHECKS):
            raise InputError("checks must list exactly the six business checks")
        if not all(v is None or type(v) is bool for v in checks.values()):
            raise InputError("check values must be true/false/null")
        if type(ev["real_business_run"]) is not bool:
            raise InputError("real_business_run must be boolean")
        sha = ev["artifact_manifest_sha256"]
        if sha is not None and not (isinstance(sha, str) and HEX64.fullmatch(sha)):
            raise InputError("artifact_manifest_sha256 must be null or 64 lowercase hex")
        ref = ev["independent_rerun_ref"]
        if ref is not None:
            _str(ref, "independent_rerun_ref")
    else:
        if ev["action"] not in ("version_change", "freeze", "unfreeze"):
            raise InputError("unknown control action")
        if ev["action"] == "version_change":
            _versions(ev["versions"])
        elif ev["versions"] is not None:
            raise InputError("versions only allowed on version_change")
        _str(ev["reason"], "reason")
        if ev["approval_ref"] is not None:
            _str(ev["approval_ref"], "approval_ref")


def parse_log(raw):
    """Validate the byte-exact hash chain and return (events, last_line_sha)."""
    if len(raw) > MAX_LOG_BYTES:
        raise InputError("log exceeds size limit")
    if raw and not raw.endswith(b"\n"):
        raise InputError("log must end with a newline (possible truncation)")
    lines = raw.split(b"\n")[:-1] if raw else []
    prev, last_ts, events = GENESIS, None, []
    for n, line in enumerate(lines, 1):
        if not line or line != line.strip():
            raise InputError(f"line {n}: blank or padded line")
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError:
            raise InputError(f"line {n}: not UTF-8") from None
        ev = _loads(text)
        if not isinstance(ev, dict) or type(ev.get("seq")) is not int or ev["seq"] != n:
            raise InputError(f"line {n}: seq must be contiguous from 1 (missing or reordered history)")
        if ev.get("prev_sha256") != prev:
            raise InputError(f"line {n}: hash chain broken (tampered or deleted history)")
        ts = ev.get("ts")
        if not isinstance(ts, str) or not TS.fullmatch(ts):
            raise InputError(f"line {n}: ts must be YYYY-MM-DDTHH:MM:SSZ")
        try:
            datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            raise InputError(f"line {n}: invalid calendar time") from None
        if last_ts is not None and ts < last_ts:
            raise InputError(f"line {n}: ts goes backwards")
        last_ts, prev = ts, hashlib.sha256(line).hexdigest()
        events.append(ev)
    return events, prev


def _norm(cfg, name):
    return cfg["alias"].get(name.casefold()) if isinstance(name, str) else None


def _authenticated(cfg, auth):
    """Only a trusted adapter's attestation counts; body text never does."""
    if not auth or auth["adapter"] not in cfg["adapters"] or not auth["evidence_ref"].strip():
        return None
    return _norm(cfg, auth["sender"])


def fold(cfg, events):
    units = {k: {"versions": dict(u["versions"]), "streak": 0, "window": [],
                 "frozen": False, "freeze_reasons": [], "counted_task_ids": []}
             for k, u in cfg["units"].items()}
    consumed_events, consumed_messages, decisions = set(), set(), []
    for ev in events:
        _check_event(ev, cfg)
        key = unit_key(ev["bot_id"], ev["capability_scope"])
        st = units.get(key)
        before = st["streak"] if st else None

        def record(effect, reason):
            decisions.append({"seq": ev["seq"], "event_id": ev["event_id"], "unit": key,
                              "effect": effect, "reason": reason, "streak_before": before,
                              "streak_after": st["streak"] if st else None})

        if ev["event_id"] in consumed_events:
            record("NOOP_REPLAY", "event_id already consumed")
            continue
        consumed_events.add(ev["event_id"])
        if st is None:
            record("REJECTED", "unknown unit")
            continue
        if ev["kind"] == "control":
            _apply_control(cfg, st, ev, record)
            continue
        if ev["status"] == "HOLD":
            record("NOOP_HOLD", "pending workflow state; no add, no subtract")
            continue
        messages = {ev["producer_message_id"], ev["verification_message_id"]}
        if messages & consumed_messages:
            record("NOOP_REPLAY", "message already consumed")
            continue
        consumed_messages |= messages
        _apply_result(cfg, cfg["units"][key], st, ev, record)
    return units, consumed_events, consumed_messages, decisions


def _reset(st, record, effect, reason):
    st["streak"], st["window"] = 0, []
    record(effect, reason)


def _apply_control(cfg, st, ev, record):
    sender = _authenticated(cfg, ev["auth"])
    if sender is None or sender not in cfg["owners"]:
        record("REJECTED", "control event lacks authenticated owner sender")
        return
    action = ev["action"]
    if action == "version_change":
        new = _versions(ev["versions"])
        if new == st["versions"]:
            record("REJECTED", "version_change without a change")
            return
        st["versions"] = new
        _reset(st, record, "CONTROL_APPLIED", "material version change invalidates streak")
    elif action == "freeze":
        st["frozen"] = True
        st["freeze_reasons"].append(ev["reason"])
        record("CONTROL_APPLIED", "frozen by owner")
    else:
        if ev["approval_ref"] is None:
            record("REJECTED", "unfreeze requires approval_ref")
            return
        st["frozen"], st["freeze_reasons"] = False, []
        record("CONTROL_APPLIED", "unfrozen with approval; streak preserved")


def _apply_result(cfg, unit, st, ev, record):
    if ev["versions"] != st["versions"]:
        record("REJECTED", "version drift: event not for current version")
        return
    outer, inner, checks = ev["outer_verdict"], ev["receipt_verdict"], ev["checks"]
    if "CONFLICT" in (outer, inner) or outer != inner:
        st["frozen"] = True
        st["freeze_reasons"].append(f"conflict at seq {ev['seq']}")
        record("CONFLICT_FROZEN", "outer/receipt verdict conflict; streak kept, upgrade frozen")
        return
    if outer == "PASS" and any(v is False for v in checks.values()):
        st["frozen"] = True
        st["freeze_reasons"].append(f"conflict at seq {ev['seq']}")
        record("CONFLICT_FROZEN", "PASS claimed with a failed inner check")
        return
    if outer == "FAIL":
        _reset(st, record, "RESET", "business failure")
        return
    if outer in ("NOT_TESTED", "BLOCKED"):
        _reset(st, record, "RESET", f"finalized {outer} breaks the chain")
        return
    # outer == inner == PASS
    if ev["task_id"] in st["counted_task_ids"]:
        record("NOOP_DUP_TASK", "task_id already contributed its one qualified count")
        return
    sender = _authenticated(cfg, ev["auth"])
    producer = _norm(cfg, ev["producer"])
    if sender is None:
        return _reset(st, record, "RESET", "BLOCKED: sender not authenticated by a trusted adapter")
    if producer is None:
        return _reset(st, record, "RESET", "BLOCKED: unknown producer identity")
    if producer != unit["producer"]:
        return _reset(st, record, "RESET", "BLOCKED: producer is not this unit's bot")
    if sender == producer:
        return _reset(st, record, "RESET", "BLOCKED: self-verification")
    if ev["producer_message_id"] == ev["verification_message_id"]:
        return _reset(st, record, "RESET", "BLOCKED: verification reuses the producer message")
    if sender not in unit["verifiers"]:
        return _reset(st, record, "RESET", "BLOCKED: verifier not allowed for this capability")
    if any(v is None for v in checks.values()) or ev["artifact_manifest_sha256"] is None \
            or ev["independent_rerun_ref"] is None:
        return _reset(st, record, "RESET", "NOT_TESTED: missing evidence breaks the chain")
    if st["frozen"]:
        record("PAUSED_FROZEN", "qualified PASS ignored while frozen")
        return
    st["streak"] += 1
    st["window"].append({"task_id": ev["task_id"], "real_business_run": ev["real_business_run"]})
    st["counted_task_ids"].append(ev["task_id"])
    record("COUNTED", "qualified business PASS")


def replay(config_raw, log_raw):
    cfg = load_config(config_raw)
    events, last_sha = parse_log(log_raw)
    units, consumed_events, consumed_messages, decisions = fold(cfg, events)
    out_units = {}
    for key, st in units.items():
        eligible = (st["streak"] >= REQUIRED_DISTINCT_TASKS and not st["frozen"]
                    and any(w["real_business_run"] for w in st["window"]))
        out_units[key] = {
            "versions": st["versions"], "streak": st["streak"], "window": st["window"],
            "frozen": st["frozen"], "freeze_reasons": st["freeze_reasons"],
            "counted_task_ids": st["counted_task_ids"],
            "evidence_stage_candidate": STAGE_CEILING if eligible else None,
            "effective_stage": None,
        }
    state = {"schema_version": "gate-state/v1", "ledger_kind": cfg["ledger_kind"],
             "last_seq": len(events), "last_line_sha256": last_sha, "units": out_units,
             "consumed_event_ids": sorted(consumed_events),
             "consumed_message_ids": sorted(consumed_messages), "decisions": decisions,
             "scope": "candidate-only; effective_stage is never written by this gate"}
    return canonical(state)


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def seal(draft_raw, start_prev=GENESIS, start_seq=1):
    """Fixture helper: add seq/prev_sha256 to draft JSONL objects."""
    out, prev = [], start_prev
    for n, line in enumerate(draft_raw.decode("utf-8").splitlines()):
        if not line.strip():
            continue
        ev = _loads(line)
        if not isinstance(ev, dict) or "seq" in ev or "prev_sha256" in ev:
            raise InputError("draft events must be objects without seq/prev_sha256")
        ev = {"seq": start_seq + len(out), "prev_sha256": prev, **ev}
        sealed = json.dumps(ev, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        prev = hashlib.sha256(sealed).hexdigest()
        out.append(sealed)
    return b"".join(line + b"\n" for line in out)


def _read(path):
    with open(path, "rb") as f:
        return f.read(MAX_LOG_BYTES + 1)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="print canonical state")
    v = sub.add_parser("verify", help="compare replayed state to a stored ledger byte-for-byte")
    for q in (r, v):
        q.add_argument("--config", required=True)
        q.add_argument("--events", required=True)
    v.add_argument("--ledger", required=True)
    s = sub.add_parser("seal", help="fixture helper: chain draft events")
    s.add_argument("draft")
    args = p.parse_args(argv)
    try:
        if args.cmd == "seal":
            sys.stdout.buffer.write(seal(_read(args.draft)))
            return 0
        state = replay(_read(args.config), _read(args.events))
        if args.cmd == "replay":
            sys.stdout.buffer.write(state)
            return 0
        stored = _read(args.ledger)
        if stored == state:
            print(json.dumps({"result": "MATCH", "sha256": hashlib.sha256(state).hexdigest()}))
            return 0
        print(json.dumps({"result": "REGRESSION", "replayed_sha256": hashlib.sha256(state).hexdigest(),
                          "ledger_sha256": hashlib.sha256(stored).hexdigest()}))
        return 1
    except InputError as error:
        print(json.dumps({"result": "INPUT_ERROR", "reason": str(error)}, ensure_ascii=False))
        return 5
    except OSError:
        print(json.dumps({"result": "INPUT_ERROR", "reason": "unreadable input file"}))
        return 5
    except Exception as error:  # unknown failure must not collide with REGRESSION (1)
        print(json.dumps({"result": "INPUT_ERROR", "reason": f"unexpected {type(error).__name__}"}))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
