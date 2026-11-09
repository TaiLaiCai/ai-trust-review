#!/usr/bin/env python3
"""event_gate v1 — 纯事件门控与可重放日志.

apply: 只追加事件到 JSONL 账本（重放 no-op、冲突冻结、版本漂移拒绝、索引断链拒绝）。
gate:  只读检查严格三任务连续链（哈希链 + 连续 task_index + 各带证据摘要）。

本工具不认证身份、不授予权限、不写实际等级；PASS 只证明本次读到的账本字节。
"""
import argparse
import hashlib
import json
import os
import re
import sys

SCHEMA = "event-gate/v1"
GENESIS = "0" * 64
ID_RE = re.compile(r"^[0-9a-z][0-9a-z-]{0,63}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_LEDGER_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 4096


class ContractError(Exception):
    """账本或事件违反契约 → exit 2."""


class GateFailure(Exception):
    """门控失败或事件被拒（断链/冻结/漂移）→ exit 1."""


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def no_dup_keys(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            raise ContractError("duplicate JSON key: %s" % k)
        seen.add(k)
    return dict(pairs)


def load_events(path):
    try:
        raw = open(path, "rb").read()
    except FileNotFoundError:
        raise ContractError("ledger not found: %s" % path)
    if len(raw) > MAX_LEDGER_BYTES:
        raise ContractError("ledger exceeds 4MiB")
    if not raw:
        return [], []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ContractError("ledger is not valid UTF-8")
    if not text.endswith("\n"):
        raise ContractError("ledger must end with newline")
    lines = [l + "\n" for l in text.split("\n")[:-1]]
    if len(lines) > MAX_EVENTS:
        raise ContractError("ledger exceeds %d events" % MAX_EVENTS)
    events = []
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line, object_pairs_hook=no_dup_keys)
        except (json.JSONDecodeError, ContractError) as e:
            raise ContractError("line %d: %s" % (i + 1, e))
        if not isinstance(obj, dict):
            raise ContractError("line %d: not an object" % (i + 1))
        events.append(obj)
    return events, lines


def check_event_shape(obj, where, require_prev=True):
    allowed = {"id", "kind", "version", "task_index", "evidence_sha256", "prev_sha256"}
    for k in obj:
        if k not in allowed:
            raise ContractError("%s: unknown field %s" % (where, k))
    for k in ("id", "kind", "version", "task_index"):
        if k not in obj:
            raise ContractError("%s: missing field %s" % (where, k))
    if require_prev and "prev_sha256" not in obj:
        raise ContractError("%s: missing field prev_sha256" % where)
    if not isinstance(obj["id"], str) or not ID_RE.match(obj["id"]):
        raise ContractError("%s: bad id" % where)
    if obj["kind"] != "task":
        raise ContractError("%s: kind must be 'task' in v1" % where)
    if not isinstance(obj["task_index"], int) or isinstance(obj["task_index"], bool) \
            or not (0 <= obj["task_index"] <= 2 ** 31):
        raise ContractError("%s: bad task_index" % where)
    if "prev_sha256" in obj and (not isinstance(obj["prev_sha256"], str)
                                 or not HEX_RE.match(obj["prev_sha256"])):
        raise ContractError("%s: bad prev_sha256" % where)
    if "evidence_sha256" in obj:
        ev = obj["evidence_sha256"]
        if not isinstance(ev, str) or not HEX_RE.match(ev):
            raise ContractError(
                "%s: evidence_sha256 must be 64 lowercase hex or absent, not %r"
                % (where, ev))
    if not isinstance(obj["version"], str):
        raise ContractError("%s: bad version" % where)


def verify_chain(events, lines):
    """校验整条哈希链、task_index 连续性与 id 唯一性；返回 (ok, reason)。"""
    prev = GENESIS
    prev_index = -1
    seen_ids = set()
    for i, (obj, line) in enumerate(zip(events, lines)):
        check_event_shape(obj, "line %d" % (i + 1))
        if obj["id"] in seen_ids:
            return False, "duplicate-id at line %d: %s" % (i + 1, obj["id"])
        seen_ids.add(obj["id"])
        if obj["version"] != SCHEMA:
            return False, "version-drift at line %d: %r" % (i + 1, obj["version"])
        if obj["prev_sha256"] != prev:
            return False, "hash-chain-broken at line %d" % (i + 1)
        if obj["task_index"] != prev_index + 1:
            return False, "index-gap at line %d: %d after %d" % (i + 1, obj["task_index"], prev_index)
        prev = sha256_hex(line.encode("utf-8"))
        prev_index = obj["task_index"]
    return True, None


def cmd_apply(args):
    events, lines = load_events(args.ledger)
    try:
        event = json.loads(args.event, object_pairs_hook=no_dup_keys)
    except (json.JSONDecodeError, ContractError) as e:
        raise ContractError("event JSON: %s" % e)
    if not isinstance(event, dict):
        raise ContractError("event must be an object")
    # prev_sha256 由账本状态决定，输入事件不得自带。
    if "prev_sha256" in event:
        raise ContractError("event must not carry prev_sha256 (derived from ledger)")
    check_event_shape(event, "event", require_prev=False)
    if event["version"] != SCHEMA:
        print(json.dumps({"action": "version-drift-invalid", "id": event["id"],
                          "version": event["version"]}, ensure_ascii=False))
        return 1
    # 已存在同 id 事件的检测提前到整链校验之前，保证 replay-noop 仍然可达。
    for i, obj in enumerate(events):
        if obj["id"] == event["id"]:
            orig_prev = sha256_hex(lines[i - 1].encode("utf-8")) if i > 0 else GENESIS
            replay = dict(event)
            replay["prev_sha256"] = orig_prev
            replay_digest = sha256_hex((canonical(replay) + "\n").encode("utf-8"))
            if sha256_hex(lines[i].encode("utf-8")) == replay_digest:
                print(json.dumps({"action": "replay-noop", "id": event["id"],
                                  "line_sha256": replay_digest}, ensure_ascii=False))
                return 0
            print(json.dumps({"action": "conflict-frozen", "id": event["id"]}, ensure_ascii=False))
            return 1
    ok, reason = verify_chain(events, lines)
    if not ok:
        raise GateFailure("ledger not appendable: %s" % reason)
    last_index = events[-1]["task_index"] if events else -1
    last_digest = sha256_hex(lines[-1].encode("utf-8")) if lines else GENESIS
    record = dict(event)
    record["prev_sha256"] = last_digest
    line = canonical(record) + "\n"
    digest = sha256_hex(line.encode("utf-8"))
    if event["task_index"] != last_index + 1:
        print(json.dumps({"action": "index-gap-rejected", "id": event["id"],
                          "expected_task_index": last_index + 1}, ensure_ascii=False))
        return 1
    fd = os.open(args.ledger, os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps({"action": "appended", "id": event["id"], "line_sha256": digest},
                     ensure_ascii=False))
    return 0


def cmd_gate(args):
    events, lines = load_events(args.ledger)
    ok, reason = verify_chain(events, lines)
    if not ok:
        print(json.dumps({"verdict": "FAIL", "reason": reason}, ensure_ascii=False))
        return 1
    if len(events) < 3:
        print(json.dumps({"verdict": "FAIL",
                          "reason": "chain-too-short: %d events, need 3" % len(events)},
                         ensure_ascii=False))
        return 1
    tail = events[-3:]
    for i, obj in enumerate(tail):
        if "evidence_sha256" not in obj:
            print(json.dumps({"verdict": "FAIL",
                              "reason": "missing-evidence at line %d (task %d): "
                                        "evidence_sha256 absent — chain broken"
                                        % (len(events) - 2 + i, obj["task_index"])},
                             ensure_ascii=False))
            return 1
    indexes = [obj["task_index"] for obj in tail]
    print(json.dumps({"verdict": "PASS", "scope": "ledger-bytes-only",
                      "task_indexes": indexes,
                      "evidence_sha256": [obj["evidence_sha256"] for obj in tail]},
                     ensure_ascii=False))
    return 0


def cmd_version(_args):
    readme = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
    print("v1 %s" % sha256_hex(open(readme, "rb").read()))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--version"]:
        return cmd_version(None)
    p = argparse.ArgumentParser(prog="event_gate")
    sub = p.add_subparsers(dest="cmd", required=True)
    ap = sub.add_parser("apply")
    ap.add_argument("ledger")
    ap.add_argument("event")
    ap.set_defaults(func=cmd_apply)
    gp = sub.add_parser("gate")
    gp.add_argument("ledger")
    gp.set_defaults(func=cmd_gate)
    vp = sub.add_parser("--version", add_help=False)
    vp.set_defaults(func=cmd_version)
    args = p.parse_args(argv)
    try:
        return args.func(args)
    except GateFailure as e:
        print(json.dumps({"action": "rejected", "reason": str(e)}, ensure_ascii=False))
        return 1
    except ContractError as e:
        print("contract error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
