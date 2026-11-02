"""C6 history component: deterministic, read-only LS-7 ratchet (not full C6)."""
from datetime import datetime
import hashlib
import json
import re

MAX_BYTES = 16 * 1024 * 1024
ZERO = "0" * 64
TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?[+-]\d\d:\d\d")
ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
HEX = re.compile(r"[0-9a-f]{64}")
STATES = {"open", "closed", "pending", "blocked"}


class InputError(ValueError):
    pass


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def timestamp(value):
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise InputError("invalid timestamp format")
    try:
        offset = value[-6:]
        if int(offset[1:3]) > 23 or int(offset[4:]) > 59:
            raise ValueError("offset")
        return datetime.fromisoformat(value)
    except ValueError:
        raise InputError("invalid calendar time or offset") from None


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON key")
        result[key] = value
    return result


def load(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise InputError("expected bounded raw bytes")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise InputError("invalid JSON bytes") from None


def nonempty(value):
    return isinstance(value, str) and bool(value) and value == value.strip()


def loops(value):
    if not isinstance(value, dict) or any(
            not nonempty(k) or not isinstance(v, str) or v not in STATES for k, v in value.items()):
        raise InputError("invalid loop states")
    return value


def identities(aliases, owners, subject):
    if not isinstance(aliases, dict) or not aliases or not isinstance(owners, list):
        raise InputError("invalid identity configuration")
    table = {}
    for stable, names in aliases.items():
        if not nonempty(stable) or not isinstance(names, list):
            raise InputError("invalid identity")
        for name in [stable] + names:
            if not nonempty(name):
                raise InputError("invalid alias")
            key = name.casefold()
            if table.get(key, stable) != stable:
                raise InputError("ambiguous alias")
            table[key] = stable
    if any(not isinstance(o, str) or o.casefold() not in table for o in owners):
        raise InputError("unknown owner")
    if not isinstance(subject, str) or subject.casefold() not in table:
        raise InputError("unknown subject")
    allowed = {table[o.casefold()] for o in owners}
    if table[subject.casefold()] in allowed:
        raise InputError("subject cannot approve its own waiver")
    return table, allowed


def verify_history(snapshots, ledger):
    if not isinstance(snapshots, dict) or not isinstance(ledger, bytes) or len(ledger) > MAX_BYTES:
        raise InputError("invalid history inputs")
    if ledger and not ledger.endswith(b"\n"):
        raise InputError("truncated ledger")
    if b"\r" in ledger:
        raise InputError("ledger must use LF, not CR or CRLF")
    seen, previous, baseline, times = set(), ZERO, set(), []
    lines = ledger[:-1].split(b"\n") if ledger else []
    for number, line in enumerate(lines, 1):
        if not line or line != line.strip():
            raise InputError("blank or padded ledger line")
        row = load(line)
        if not isinstance(row, dict) or set(row) != {"seq", "prev_sha256", "snapshot_id", "sha256"}:
            raise InputError("ledger fields mismatch")
        sid, sha = row["snapshot_id"], row["sha256"]
        if type(row["seq"]) is not int or row["seq"] != number or row["prev_sha256"] != previous:
            raise InputError("ledger sequence or chain broken")
        if not isinstance(sid, str) or not ID.fullmatch(sid) or sid in seen:
            raise InputError("invalid or duplicate snapshot id")
        if not isinstance(sha, str) or not HEX.fullmatch(sha):
            raise InputError("invalid snapshot digest")
        if sid not in snapshots:
            raise InputError("missing historical snapshot")
        raw = snapshots[sid]
        snap = load(raw)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise InputError("historical snapshot changed")
        if not isinstance(snap, dict) or set(snap) != {"ts", "loops"}:
            raise InputError("snapshot fields mismatch")
        ts = timestamp(snap["ts"])
        if times and ts <= times[-1]:
            raise InputError("historical timestamps not strictly increasing")
        times.append(ts)
        baseline.update(k for k, state in loops(snap["loops"]).items() if state == "closed")
        seen.add(sid)
        previous = hashlib.sha256(line).hexdigest()
    if seen != set(snapshots):
        raise InputError("unregistered historical snapshot")
    return baseline, times, previous


def assess(snapshots, ledger, current, ts, waivers, aliases, owners, *,
           subject=None, expected_head_sha256=None, min_seq=None):
    """Return (exit, canonical JSON). All failure paths are input error 5."""
    try:
        now = timestamp(ts)
        current = loops(current)
        table, allowed = identities(aliases, owners, subject)
        if (type(min_seq) is not int or min_seq < 0 or
                not isinstance(expected_head_sha256, str) or not HEX.fullmatch(expected_head_sha256)):
            raise InputError("trusted history head and minimum sequence are required")
        baseline, times, last_sha = verify_history(snapshots, ledger)
        if len(times) < min_seq or last_sha != expected_head_sha256:
            raise InputError("history does not match trusted checkpoint")
        if times and now <= max(times):
            raise InputError("current timestamp must be later than all history")
        if not isinstance(waivers, list):
            raise InputError("waivers must be a list")
        waived = set()
        for waiver in waivers:
            if not isinstance(waiver, dict) or set(waiver) != {"loop", "reason", "approved_by", "ts"}:
                raise InputError("waiver fields mismatch")
            if not all(nonempty(waiver[k]) for k in waiver):
                raise InputError("empty waiver field")
            if waiver["loop"] in waived:
                raise InputError("duplicate waiver loop")
            if table.get(waiver["approved_by"].casefold()) not in allowed:
                raise InputError("waiver owner is not allowed")
            waiver_time = timestamp(waiver["ts"])
            if waiver_time > now or (times and waiver_time <= times[-1]):
                raise InputError("waiver must be later than latest history and no later than now")
            waived.add(waiver["loop"])
        regressions = sorted(k for k in baseline if current.get(k) != "closed")
        pending = sorted(set(regressions) & waived)
        code = 0 if not regressions else 3 if len(pending) == len(regressions) else 1
        result = {"ts": ts, "loops": current, "baseline": sorted(baseline),
                  "regressions": regressions, "waived_pending": pending,
                  "last_history_sha256": last_sha, "history_seq": len(times),
                  "result": {0: "NO_REGRESSION", 1: "REGRESSION", 3: "WAIVED_PENDING"}[code],
                  "scope": "history integrity only; no closure authentication or stage changes"}
        return code, canonical(result)
    except Exception as error:
        return 5, canonical({"result": "INPUT_ERROR", "reason": str(error)})
