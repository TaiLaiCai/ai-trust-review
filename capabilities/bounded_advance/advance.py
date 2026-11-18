#!/usr/bin/env python3
"""Run one finite, pre-authorized plan. No shell, no timer, no network.

A delivery executes remaining units in order. Completed units are not run
again. A mismatch or rejected input stops the plan. A later process can
continue the same delivery only when the ledger shows a successful prefix
and no stop. This does not call an independent reviewer or an external quota.
"""
import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA = "bounded-advance/v1"
ZERO = "0" * 64
MAX_UNITS = 16
MAX_PLAN_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024


class ContractError(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key")
        result[key] = value
    return result


def load_json(raw):
    if len(raw) > MAX_PLAN_BYTES:
        raise ContractError("plan exceeds byte limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ContractError("plan is not UTF-8 JSON") from None
    return value


def hex_sha(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ContractError(f"invalid {label}")
    return value


def load_plan(raw):
    plan = load_json(raw)
    if not isinstance(plan, dict) or set(plan) != {"schema", "plan_id", "input_sha256", "units"}:
        raise ContractError("plan fields mismatch")
    if plan["schema"] != SCHEMA:
        raise ContractError("unsupported schema")
    plan_id = plan["plan_id"]
    if not isinstance(plan_id, str) or not plan_id or len(plan_id) > 64:
        raise ContractError("invalid plan_id")
    units = plan["units"]
    if not isinstance(units, list) or not units or len(units) > MAX_UNITS:
        raise ContractError("plan needs 1..16 units")
    seen = set()
    normalized = []
    for unit in units:
        if not isinstance(unit, dict) or set(unit) != {"id", "argv", "stdin_sha256", "expected_exit"}:
            raise ContractError("unit fields mismatch")
        unit_id = unit["id"]
        if not isinstance(unit_id, str) or not unit_id or len(unit_id) > 64 or unit_id in seen:
            raise ContractError("invalid or duplicate unit id")
        seen.add(unit_id)
        argv = unit["argv"]
        if not isinstance(argv, list) or not argv or len(argv) > 16:
            raise ContractError("invalid argv")
        if any(not isinstance(part, str) or not part or len(part.encode()) > 4096 for part in argv):
            raise ContractError("invalid argv item")
        expect = unit["expected_exit"]
        if type(expect) is not int or not 0 <= expect <= 255:
            raise ContractError("invalid expected_exit")
        stdin_sha = unit["stdin_sha256"]
        if stdin_sha is not None:
            hex_sha(stdin_sha, "stdin_sha256")
        normalized.append(unit)
    hex_sha(plan["input_sha256"], "input_sha256")
    plan["units"] = normalized
    return plan


def read_ledger(path):
    if not path.exists():
        return []
    raw = path.read_bytes()
    if not raw:
        return []
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise ContractError("ledger must be LF-terminated lines")
    rows = []
    previous = ZERO
    for line in raw[:-1].split(b"\n"):
        if not line:
            raise ContractError("blank ledger line")
        try:
            row = json.loads(line.decode("utf-8"), object_pairs_hook=unique_pairs)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ContractError("corrupt ledger") from None
        if row.get("prev_sha256") != previous:
            raise ContractError("ledger chain broken")
        previous = sha256(line + b"\n")
        rows.append(row)
    return rows


def append_row(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_bytes() if path.exists() else b""
    previous = sha256(existing[:-1].split(b"\n")[-1] + b"\n") if existing else ZERO
    if existing and not existing.endswith(b"\n"):
        raise ContractError("ledger must be LF-terminated lines")
    row = dict(row)
    row["seq"] = existing.count(b"\n") + 1 if existing else 1
    row["prev_sha256"] = previous
    blob = canonical(row)
    with path.open("ab") as handle:
        handle.write(blob)
        handle.flush()
        os.fsync(handle.fileno())
    return row


def plan_rows(rows, plan_id, plan_sha):
    return [row for row in rows if row.get("plan_id") == plan_id and row.get("plan_sha256") == plan_sha]


def advance(plan_raw, input_bytes, stdin_by_unit, ledger_path, delivery_id, cwd,
            max_steps=None, fault=None, binding=None):
    if not isinstance(delivery_id, str) or not delivery_id or len(delivery_id) > 64:
        raise ContractError("invalid delivery_id")
    if not isinstance(input_bytes, bytes):
        raise ContractError("input must be bytes")
    plan = load_plan(plan_raw)
    # 账本绑定整份计划的规范化指纹：argv/stdin/期望值任一变化即不同计划，拒绝复用进度。
    plan_sha = sha256(canonical(plan))
    cwd = Path(cwd)
    if not cwd.is_dir():
        raise ContractError("cwd is not a directory")
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    # 同一账本上的并发投递用排它锁串行化：同一单元不会被两个进程同时执行。
    with open(str(ledger_path) + ".lock", "a+b") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            return _advance_locked(plan, plan_sha, input_bytes, stdin_by_unit,
                                   ledger_path, delivery_id, cwd, max_steps, fault, binding)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _note(binding):
    note = {"actor_role": "consumer"}
    if not binding:
        return note
    for key in ("producer_version", "reviewer_version"):
        value = binding.get(key)
        if value is not None:
            note[key] = value
    return note


def _advance_locked(plan, plan_sha, input_bytes, stdin_by_unit, ledger_path, delivery_id, cwd,
                    max_steps, fault, binding):
    rows = read_ledger(ledger_path)
    matched = plan_rows(rows, plan["plan_id"], plan_sha)
    if any(row.get("status") in {"mismatch", "rejected", "uncertain"} for row in matched):
        return {"status": "stopped", "executed": [], "reason": "plan already stopped"}
    same_id_other_plan = [row for row in rows
                          if row.get("plan_id") == plan["plan_id"]
                          and row.get("plan_sha256") != plan_sha]
    if same_id_other_plan:
        return {"status": "stopped", "executed": [],
                "reason": "plan changed: existing progress is bound to a different plan fingerprint"}
    for unit in plan["units"]:
        last = None
        for row in matched:
            if row.get("unit_id") == unit["id"]:
                last = row.get("status")
        if last == "claimed":
            append_row(ledger_path, {
                "delivery_id": delivery_id, "plan_id": plan["plan_id"], "plan_sha256": plan_sha,
                "input_sha256": plan["input_sha256"], "unit_id": unit["id"], "status": "uncertain",
                "exit_code": None, "expected_exit": unit["expected_exit"],
                "stdout_sha256": None, "stderr_sha256": None,
                "detail": "claim without completion; execution uncertain; not re-executed",
                **_note(binding),
            })
            return {"status": "stopped", "executed": [], "reason": "uncertain claim; not re-executed"}
    done = {row["unit_id"] for row in matched if row.get("status") == "ok"}
    if sha256(input_bytes) != plan["input_sha256"]:
        # 拒绝记录按计划声明的 sha 归档，实际输入 sha 另记；同计划随后任何投递都停。
        append_row(ledger_path, {
            "delivery_id": delivery_id, "plan_id": plan["plan_id"], "plan_sha256": plan_sha,
            "input_sha256": plan["input_sha256"],
            "actual_input_sha256": sha256(input_bytes),
            "unit_id": "-", "status": "rejected", "exit_code": None, "expected_exit": None,
            "stdout_sha256": None, "stderr_sha256": None,
            "detail": "input bytes do not match plan input_sha256",
            **_note(binding),
        })
        return {"status": "rejected", "executed": [], "reason": "input_sha256 mismatch"}
    executed = []
    for unit in plan["units"]:
        if unit["id"] in done:
            continue
        if max_steps is not None and len(executed) >= max_steps:
            return {"status": "partial", "executed": executed, "reason": "invocation budget reached"}
        stdin = stdin_by_unit.get(unit["id"], b"")
        if not isinstance(stdin, bytes):
            raise ContractError("stdin must be bytes")
        expected_stdin = unit["stdin_sha256"]
        if expected_stdin is None:
            stdin_ok = stdin == b""
        else:
            # 显式声明的空 stdin（sha256(b"")）也是合法绑定。
            stdin_ok = sha256(stdin) == expected_stdin
        if not stdin_ok:
            append_row(ledger_path, {
                "delivery_id": delivery_id, "plan_id": plan["plan_id"], "plan_sha256": plan_sha,
                "input_sha256": plan["input_sha256"], "unit_id": unit["id"], "status": "rejected",
                "exit_code": None, "expected_exit": unit["expected_exit"],
                "stdout_sha256": None, "stderr_sha256": None, "detail": "stdin sha mismatch",
                **_note(binding),
            })
            return {"status": "rejected", "executed": executed, "reason": "stdin_sha256 mismatch"}
        append_row(ledger_path, {
            "delivery_id": delivery_id, "plan_id": plan["plan_id"], "plan_sha256": plan_sha,
            "input_sha256": plan["input_sha256"], "unit_id": unit["id"], "status": "claimed",
            "exit_code": None, "expected_exit": unit["expected_exit"],
            "stdout_sha256": None, "stderr_sha256": None,
            "argv_sha256": sha256(canonical(unit["argv"])), "detail": "claimed before exec",
            **_note(binding),
        })
        if fault == "after_claim":
            return {"status": "partial", "executed": executed, "reason": "fault after claim"}
        try:
            proc = subprocess.run(unit["argv"], cwd=cwd, input=stdin, capture_output=True, shell=False)
        except OSError as error:
            append_row(ledger_path, {
                "delivery_id": delivery_id, "plan_id": plan["plan_id"], "plan_sha256": plan_sha,
                "input_sha256": plan["input_sha256"], "unit_id": unit["id"], "status": "rejected",
                "exit_code": 127, "expected_exit": unit["expected_exit"],
                "stdout_sha256": sha256(b""), "stderr_sha256": sha256(str(error).encode()),
                "detail": "spawn failed", **_note(binding),
            })
            return {"status": "stopped", "executed": executed, "reason": "spawn failed"}
        if fault == "after_exec":
            return {"status": "partial", "executed": executed + [unit["id"]], "reason": "fault after exec"}
        too_large = len(proc.stdout) > MAX_OUTPUT_BYTES or len(proc.stderr) > MAX_OUTPUT_BYTES
        if too_large:
            status, detail = "rejected", "output exceeds byte limit"
        elif proc.returncode == unit["expected_exit"]:
            status, detail = "ok", None
        else:
            status, detail = "mismatch", "exit mismatch"
        append_row(ledger_path, {
            "delivery_id": delivery_id, "plan_id": plan["plan_id"], "plan_sha256": plan_sha,
            "input_sha256": plan["input_sha256"],
            "unit_id": unit["id"], "status": status, "exit_code": proc.returncode,
            "expected_exit": unit["expected_exit"], "stdout_sha256": sha256(proc.stdout),
            "stderr_sha256": sha256(proc.stderr), "detail": detail, **_note(binding),
        })
        executed.append(unit["id"])
        if status != "ok":
            return {"status": "stopped", "executed": executed, "reason": "exit mismatch"}
    return {"status": "complete", "executed": executed, "reason": None}


def _under_queue(queue, raw_path):
    if not isinstance(raw_path, str) or not raw_path or raw_path.startswith("/") or "\\" in raw_path:
        raise ContractError("queue path must be relative")
    path = (queue / raw_path).resolve()
    if queue.resolve() not in path.parents and path != queue.resolve():
        raise ContractError("queue path escapes the queue directory")
    return path


def consume_one(queue):
    """Run at most one pre-authorized unit. Never appends authorizations."""
    auth_path = queue / "authorized.jsonl"
    if not auth_path.exists():
        return {"status": "idle", "executed": [], "reason": "no authorization file"}
    raw = auth_path.read_bytes()
    if not raw:
        return {"status": "idle", "executed": [], "reason": "no authorized tasks"}
    if not raw.endswith(b"\n"):
        raise ContractError("authorized.jsonl must be LF-terminated")
    for line in raw[:-1].split(b"\n"):
        item = json.loads(line.decode("utf-8"), object_pairs_hook=unique_pairs)
        plan_path = _under_queue(queue, item.get("plan"))
        input_path = _under_queue(queue, item.get("input"))
        delivery = item.get("delivery")
        cwd = _under_queue(queue, item["cwd"]) if item.get("cwd") else queue
        stdin_by_unit = {}
        for unit_id, rel in (item.get("stdin") or {}).items():
            stdin_by_unit[unit_id] = _under_queue(queue, rel).read_bytes()
        binding = {
            "producer_version": item.get("producer_version"),
            "reviewer_version": item.get("reviewer_version"),
        }
        result = advance(
            plan_path.read_bytes(), input_path.read_bytes(), stdin_by_unit,
            queue / "ledger.jsonl", delivery, cwd, max_steps=1, binding=binding,
        )
        if result["executed"] or result["status"] == "partial":
            return result
        # A recorded rejection stops only that authorization. Later lines stay eligible.
    return {"status": "idle", "executed": [], "reason": "no runnable authorized task"}


def open_wake(path):
    if not path.exists():
        os.mkfifo(path, 0o600)
    read_fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    hold_fd = os.open(path, os.O_WRONLY)
    os.set_blocking(read_fd, True)
    return read_fd, hold_fd


def serve(queue_dir, once=False):
    """Consume the authorized queue. Idle wait is one blocking read, not a poll."""
    queue = Path(queue_dir)
    if not queue.is_dir():
        raise ContractError("queue is not a directory")
    if once:
        return consume_one(queue)
    read_fd, hold_fd = open_wake(queue / "wake.fifo")
    (queue / "ready").write_text("waiting\n")
    try:
        while True:
            result = consume_one(queue)
            if result["status"] == "partial" or result["executed"]:
                continue
            os.read(read_fd, 1)
    finally:
        os.close(read_fd)
        os.close(hold_fd)


def main(argv):
    parser = argparse.ArgumentParser(description="advance one finite pre-authorized plan")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--delivery")
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--stdin", action="append", default=[], metavar="UNIT=PATH")
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.queue:
        result = serve(args.queue, once=args.once)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] in {"complete", "partial", "idle"} else 1
    if not (args.plan and args.input and args.ledger and args.delivery and args.cwd):
        raise ContractError("plan mode needs --plan --input --ledger --delivery --cwd")
    stdin_by_unit = {}
    for item in args.stdin:
        unit_id, separator, path = item.partition("=")
        if not separator:
            raise ContractError("stdin must be UNIT=PATH")
        stdin_by_unit[unit_id] = Path(path).read_bytes()
    result = advance(
        args.plan.read_bytes(), args.input.read_bytes(), stdin_by_unit,
        args.ledger, args.delivery, args.cwd, args.max_steps,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"complete", "partial"} else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except ContractError as error:
        print(json.dumps({"status": "contract_error", "reason": str(error)}, ensure_ascii=False))
        sys.exit(2)
