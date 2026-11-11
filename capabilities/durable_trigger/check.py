#!/usr/bin/env python3
"""durable_trigger v1 — 持久触发、锁、游标、重启续作、原子应用与读回、失败恢复.

子命令：
  enqueue      把一个触发追加到持久队列（只追加 JSONL）。
  approve      为某个版本化候选登记批准（记录候选字节摘要，不认证批准人）。
  baseline     记录平台目录基线（每 Bot 一个 JSON 文件）。
  trigger      取租约、消费游标指向的触发、原子应用、平台读回、写审计。
  rollback     把某次已应用的变更原子回滚到应用前字节。
  kill-switch  急停开关：启用后停止新应用，回滚仍允许。
  status       只读打印状态摘要。
  verify       只读核对状态、队列、平台与审计的一致性。
  --version    打印 v1 与本能力 README 的 sha256。

本工具不认证身份、不授予权限、不写实际信任等级；退出 0 只表示本次读到的字节
与状态满足契约。租约锁是协作锁，不是内核锁；没有 OS 级强制隔离。
"""
import argparse
import errno
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

VERSION = "v2"
# 触发记录本身的字段格式未变，沿用 durable-trigger/v1；变的是本工具的行为
# （作业续作与中止语义）与状态文件格式（新增作业字段）。
SCHEMA = "durable-trigger/v1"
STATE_SCHEMA = "durable-trigger-state/v2"

MAX_QUEUE_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 4096
MAX_AUDIT_BYTES = 4 * 1024 * 1024
MAX_CANDIDATE_BYTES = 1024 * 1024
MAX_PLATFORM_BYTES = 1024 * 1024

ID_RE = re.compile(r"^[0-9a-z][0-9a-z-]{0,63}$")
BOT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CANDIDATE_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")

TRIGGER_FIELDS = ("id", "seq", "version", "target_bot", "candidate_version")
CANDIDATE_FIELDS = ("candidate_version", "bot", "stage", "config")
JOB_STATUSES = ("APPLY_PENDING", "APPLIED", "ROLLED_BACK", "ABORTED")
INJECT_POINTS = ("APPLY", "READBACK", "OTHER_BOT")

LOCK_NAME = ".durable-trigger.lock"
LOCK_TTL_SECONDS = 120.0

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_CONTRACT = 2


class ContractError(Exception):
    """输入或契约错误 → exit 2."""


class Rejected(Exception):
    """运行期拒绝 → exit 1，携带 payload."""

    def __init__(self, payload):
        super().__init__(payload.get("action", "rejected"))
        self.payload = payload


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def no_dup_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ContractError("duplicate JSON key: %s" % key)
        seen.add(key)
    return dict(pairs)


def parse_json(raw, where):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ContractError("%s: not valid UTF-8" % where)
    try:
        obj = json.loads(text, object_pairs_hook=no_dup_keys)
    except ContractError:
        raise
    except ValueError as exc:
        raise ContractError("%s: invalid JSON: %s" % (where, exc))
    return obj


def read_file_bytes(path, where, max_bytes):
    """读普通文件原始字节；拒绝符号链接与超限。"""
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        raise ContractError("%s: not found: %s" % (where, path))
    except OSError as exc:
        raise ContractError("%s: cannot read: %s (%s)" % (where, path, exc.strerror))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ContractError("%s: not a regular file: %s" % (where, path))
        if st.st_size > max_bytes:
            raise ContractError("%s: exceeds %d bytes: %s" % (where, max_bytes, path))
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ContractError("%s: exceeds %d bytes: %s" % (where, max_bytes, path))
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def write_atomic(path, data, mode=0o600):
    """写临时文件 → fsync → rename → fsync 目录。"""
    path = str(path)
    directory = os.path.dirname(path) or "."
    tmp = os.path.join(directory, "." + os.path.basename(path) + ".durable-trigger.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def fsync_dir(path):
    dir_fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def now_iso(ts=None):
    if ts is None:
        ts = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False))


# --------------------------------------------------------------------------
# 目录布局与协作锁
# --------------------------------------------------------------------------

def ensure_layout(root):
    for directory in (root, root / "candidates", root / "platform", root / "backups"):
        try:
            os.makedirs(str(directory), mode=0o700, exist_ok=True)
        except OSError as exc:
            raise ContractError("cannot create %s: %s" % (directory, exc.strerror))


def acquire_lock(root):
    """短生命周期的互斥锁，防止两个进程交错做「读状态→改状态→写状态」。"""
    path = root / LOCK_NAME
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > LOCK_TTL_SECONDS:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            return None
        else:
            try:
                os.write(fd, ("%d\n" % os.getpid()).encode("utf-8"))
            finally:
                os.close(fd)
            return path
    return None


def release_lock(path):
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------

def default_state():
    return {
        "schema_version": STATE_SCHEMA,
        "cursor_seq": -1,
        "consumed": {},
        "jobs": {},
        "lease": {"holder": None, "token": 0, "expires_at": 0.0},
        "approvals": {},
        "platform_baseline": {},
        "kill_switch": {"engaged": False, "reason": None, "at": None},
    }


def validate_state(state):
    if not isinstance(state, dict):
        raise ContractError("state must be an object")
    if state.get("schema_version") != STATE_SCHEMA:
        raise ContractError("state schema_version must be %s" % STATE_SCHEMA)
    for key in default_state():
        if key not in state:
            raise ContractError("state: missing field %s" % key)
    for key in state:
        if key not in default_state():
            raise ContractError("state: unknown field %s" % key)
    if not isinstance(state["cursor_seq"], int) or isinstance(state["cursor_seq"], bool):
        raise ContractError("state: cursor_seq must be an integer")
    for name in ("consumed", "jobs", "approvals", "platform_baseline"):
        if not isinstance(state[name], dict):
            raise ContractError("state: %s must be an object" % name)
    lease = state["lease"]
    if not isinstance(lease, dict) or set(lease) != {"holder", "token", "expires_at"}:
        raise ContractError("state: lease must have holder/token/expires_at")
    if not isinstance(lease["token"], int) or isinstance(lease["token"], bool) or lease["token"] < 0:
        raise ContractError("state: lease.token must be a non-negative integer")
    if not isinstance(lease["expires_at"], (int, float)):
        raise ContractError("state: lease.expires_at must be a number")
    kill = state["kill_switch"]
    if not isinstance(kill, dict) or set(kill) != {"engaged", "reason", "at"}:
        raise ContractError("state: kill_switch must have engaged/reason/at")
    if not isinstance(kill["engaged"], bool):
        raise ContractError("state: kill_switch.engaged must be a boolean")
    for jid, job in state["jobs"].items():
        if not isinstance(job, dict):
            raise ContractError("state: job %s must be an object" % jid)
        if job.get("status") not in JOB_STATUSES:
            raise ContractError("state: job %s has unknown status %r" % (jid, job.get("status")))
        if "aborted" in job and not isinstance(job["aborted"], bool):
            raise ContractError("state: job %s aborted must be a boolean" % jid)
        if job.get("candidate_sha256") is not None \
                and not (isinstance(job["candidate_sha256"], str)
                         and HEX_RE.match(job["candidate_sha256"])):
            raise ContractError("state: job %s candidate_sha256 must be a sha256 digest" % jid)
    for bot, digest in state["platform_baseline"].items():
        if not isinstance(digest, str) or not HEX_RE.match(digest):
            raise ContractError("state: platform_baseline[%s] must be a sha256 digest" % bot)
    return state


def load_state(root):
    path = root / "state.json"
    if not path.exists():
        return default_state()
    raw = read_file_bytes(path, "state", MAX_QUEUE_BYTES)
    if not raw.strip():
        return default_state()
    return validate_state(parse_json(raw, "state.json"))


def save_state(root, state):
    write_atomic(root / "state.json", (canonical(state) + "\n").encode("utf-8"))


# --------------------------------------------------------------------------
# 队列
# --------------------------------------------------------------------------

def load_queue(root):
    """读队列文件，返回按文件顺序排列的触发列表。"""
    path = root / "queue.jsonl"
    if not path.exists():
        return []
    raw = read_file_bytes(path, "queue", MAX_QUEUE_BYTES)
    if not raw:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ContractError("queue: not valid UTF-8")
    if not text.endswith("\n"):
        raise ContractError("queue: must end with a newline")
    lines = [l + "\n" for l in text.split("\n")[:-1]]
    if len(lines) > MAX_EVENTS:
        raise ContractError("queue: exceeds %d triggers" % MAX_EVENTS)
    triggers = []
    for i, line in enumerate(lines):
        obj = parse_json(line.encode("utf-8"), "queue line %d" % (i + 1))
        triggers.append(validate_trigger(obj, "queue line %d" % (i + 1)))
    return triggers


def validate_trigger(obj, where):
    if not isinstance(obj, dict):
        raise ContractError("%s: trigger must be an object" % where)
    for key in obj:
        if key not in TRIGGER_FIELDS:
            raise ContractError("%s: unknown field %s" % (where, key))
    for key in TRIGGER_FIELDS:
        if key not in obj:
            raise ContractError("%s: missing field %s" % (where, key))
    if not isinstance(obj["id"], str) or not ID_RE.match(obj["id"]):
        raise ContractError("%s: id must match %s" % (where, ID_RE.pattern))
    if not isinstance(obj["seq"], int) or isinstance(obj["seq"], bool) or obj["seq"] < 0:
        raise ContractError("%s: seq must be a non-negative integer" % where)
    if obj["version"] != SCHEMA:
        raise ContractError("%s: version must be %s" % (where, SCHEMA))
    if not isinstance(obj["target_bot"], str) or not BOT_RE.match(obj["target_bot"]):
        raise ContractError("%s: target_bot must match %s" % (where, BOT_RE.pattern))
    if not isinstance(obj["candidate_version"], str) \
            or not CANDIDATE_VERSION_RE.match(obj["candidate_version"]):
        raise ContractError("%s: candidate_version must match %s"
                            % (where, CANDIDATE_VERSION_RE.pattern))
    return obj


# --------------------------------------------------------------------------
# 候选与平台
# --------------------------------------------------------------------------

def candidate_path(root, version):
    return root / "candidates" / ("%s.json" % version)


def load_candidate(root, version):
    path = candidate_path(root, version)
    raw = read_file_bytes(path, "candidate", MAX_CANDIDATE_BYTES)
    obj = parse_json(raw, "candidate %s" % version)
    if not isinstance(obj, dict):
        raise ContractError("candidate %s: must be an object" % version)
    for key in obj:
        if key not in CANDIDATE_FIELDS:
            raise ContractError("candidate %s: unknown field %s" % (version, key))
    for key in ("candidate_version", "bot", "stage"):
        if key not in obj:
            raise ContractError("candidate %s: missing field %s" % (version, key))
    if obj["candidate_version"] != version:
        raise ContractError("candidate %s: candidate_version mismatch" % version)
    if not isinstance(obj["bot"], str) or not BOT_RE.match(obj["bot"]):
        raise ContractError("candidate %s: bot must match %s" % (version, BOT_RE.pattern))
    if not isinstance(obj["stage"], int) or isinstance(obj["stage"], bool) \
            or not (0 <= obj["stage"] <= 4):
        raise ContractError("candidate %s: stage must be an integer 0..4" % version)
    if "config" in obj and not isinstance(obj["config"], dict):
        raise ContractError("candidate %s: config must be an object" % version)
    return raw, obj


def platform_path(root, bot):
    return root / "platform" / ("%s.json" % bot)


def platform_digest(root, bot):
    path = platform_path(root, bot)
    if not path.exists():
        return None
    return sha256_hex(read_file_bytes(path, "platform %s" % bot, MAX_PLATFORM_BYTES))


def platform_bots(root):
    directory = root / "platform"
    if not directory.is_dir():
        return []
    bots = []
    for name in sorted(os.listdir(str(directory))):
        if not name.endswith(".json"):
            continue
        bot = name[:-len(".json")]
        if not BOT_RE.match(bot):
            raise ContractError("platform: bad bot file name %r" % name)
        bots.append(bot)
    return bots


def expected_state(state):
    """平台期望状态 = 基线 + 已被应用的作业结果。"""
    expected = dict(state["platform_baseline"])
    jobs = sorted(state["jobs"].items(), key=lambda kv: kv[1].get("seq", -1))
    for _jid, job in jobs:
        if job.get("status") == "APPLIED" and job.get("after_sha256"):
            expected[job["target_bot"]] = job["after_sha256"]
    return expected


# --------------------------------------------------------------------------
# 审计
# --------------------------------------------------------------------------

def audit(root, entry):
    line = canonical(entry) + "\n"
    fd = os.open(str(root / "audit.jsonl"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def load_audit(root):
    path = root / "audit.jsonl"
    if not path.exists():
        return []
    raw = read_file_bytes(path, "audit", MAX_AUDIT_BYTES)
    if not raw:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ContractError("audit: not valid UTF-8")
    if not text.endswith("\n"):
        raise ContractError("audit: must end with a newline")
    entries = []
    for i, line in enumerate(text.split("\n")[:-1]):
        obj = parse_json((line + "\n").encode("utf-8"), "audit line %d" % (i + 1))
        if not isinstance(obj, dict):
            raise ContractError("audit line %d: must be an object" % (i + 1))
        entries.append(obj)
    return entries


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------

def cmd_enqueue(args):
    root = Path(args.root).resolve()
    ensure_layout(root)
    raw = read_file_bytes(args.trigger, "trigger", MAX_CANDIDATE_BYTES)
    trigger = validate_trigger(parse_json(raw, "trigger"), "trigger")
    triggers = load_queue(root)
    for existing in triggers:
        if existing["id"] != trigger["id"]:
            continue
        if canonical(existing) == canonical(trigger):
            emit({"action": "duplicate-noop", "id": trigger["id"], "seq": trigger["seq"]})
            return EXIT_OK
        raise Rejected({"action": "conflict-frozen", "id": trigger["id"],
                        "reason": "same id with different content"})
    for existing in triggers:
        if existing["seq"] == trigger["seq"] and existing["id"] != trigger["id"]:
            raise Rejected({"action": "conflict-frozen", "id": trigger["id"],
                            "reason": "seq %d is already bound to id %s"
                                      % (trigger["seq"], existing["id"])})
    line = (canonical(trigger) + "\n").encode("utf-8")
    fd = os.open(str(root / "queue.jsonl"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_dir(root)
    emit({"action": "enqueued", "id": trigger["id"], "seq": trigger["seq"],
          "line_sha256": sha256_hex(line)})
    return EXIT_OK


def cmd_approve(args):
    root = Path(args.root).resolve()
    ensure_layout(root)
    version = args.candidate_version
    raw, _obj = load_candidate(root, version)
    digest = sha256_hex(raw)
    with_lock(root, lambda: _approve_locked(root, version, digest, args.approver))
    return EXIT_OK


def _approve_locked(root, version, digest, approver):
    state = load_state(root)
    state["approvals"][version] = {
        "candidate_sha256": digest,
        "approver": approver,
        "approved_at": now_iso(),
    }
    save_state(root, state)
    audit(root, {"ts": now_iso(), "action": "approved", "candidate_version": version,
                 "candidate_sha256": digest, "approver": approver})
    emit({"action": "approved", "candidate_version": version, "candidate_sha256": digest,
          "approver": approver})
    return EXIT_OK


def cmd_baseline(args):
    root = Path(args.root).resolve()
    ensure_layout(root)
    bots = platform_bots(root)
    if not bots:
        raise ContractError("platform: no bot files to baseline")
    baseline = {}
    for bot in bots:
        baseline[bot] = platform_digest(root, bot)
    with_lock(root, lambda: _baseline_locked(root, baseline))
    return EXIT_OK


def _baseline_locked(root, baseline):
    state = load_state(root)
    state["platform_baseline"] = baseline
    save_state(root, state)
    audit(root, {"ts": now_iso(), "action": "baseline-captured", "bots": sorted(baseline)})
    emit({"action": "baseline-captured", "bots": sorted(baseline),
          "platform_baseline": baseline})
    return EXIT_OK


def with_lock(root, fn):
    lock = acquire_lock(root)
    if lock is None:
        raise Rejected({"action": "lock-busy", "reason": "another process holds the state lock"})
    try:
        return fn()
    finally:
        release_lock(lock)


def cmd_trigger(args):
    root = Path(args.root).resolve()
    ensure_layout(root)
    with_lock(root, lambda: _trigger_locked(root, args))
    return EXIT_OK


def _trigger_locked(root, args):
    state = load_state(root)
    lease = state["lease"]
    now = time.time()

    if args.lease_token is not None and args.lease_token != lease["token"]:
        raise Rejected({"action": "stale-lease", "expected_token": lease["token"],
                        "got_token": args.lease_token})
    if lease["holder"] and lease["expires_at"] > now and lease["holder"] != args.holder:
        raise Rejected({"action": "lease-held", "holder": lease["holder"],
                        "expires_at": lease["expires_at"]})

    # 租约世代推进的两种情形，必须分开对待：
    #   - 租约仍然活着且属于别人 → 已在上面拒绝（lease-held）。
    #   - 租约已经过期 → 新持有者接管，旧世代的作业必须能被续作，
    #     否则一次崩溃就会让作业永远卡在 APPLY_PENDING（游标再也走不动）。
    # 因此 fencing 只拦「活着的租约被冒充」，不拦「过期后的接管」。
    old_lease = dict(lease)
    lease_expired = bool(old_lease["holder"]) and old_lease["expires_at"] <= now
    if old_lease["holder"] == args.holder and old_lease["expires_at"] > now:
        token = old_lease["token"]
    else:
        token = old_lease["token"] + 1
    state["lease"] = {"holder": args.holder, "token": token,
                      "expires_at": now + args.lease_seconds}
    save_state(root, state)

    triggers = load_queue(root)
    seen = {}
    for trigger in triggers:
        tid = trigger["id"]
        if tid in seen:
            if canonical(seen[tid]) == canonical(trigger):
                continue  # 同一投递重复出现：只消费一次
            raise Rejected({"action": "conflict-frozen", "id": tid,
                            "reason": "same id with different content in queue"})
        seen[tid] = trigger
    by_seq = {}
    for trigger in seen.values():
        if trigger["seq"] in by_seq:
            raise Rejected({"action": "conflict-frozen", "id": trigger["id"],
                            "reason": "seq %d is bound to two ids" % trigger["seq"]})
        by_seq[trigger["seq"]] = trigger
    unique = list(seen.values())

    next_seq = state["cursor_seq"] + 1

    # 续作优先：只有当待续作业正好位于游标位时才续作，否则先向前消费，
    # 等游标走到那一格自然续作。
    pending = sorted(
        ((jid, job) for jid, job in state["jobs"].items()
         if job["status"] == "APPLY_PENDING"),
        key=lambda item: item[1].get("seq", -1))
    for jid, job in pending:
        if job.get("seq") != next_seq:
            continue
        match = seen.get(jid)
        if not match:
            raise Rejected({"action": "conflict-frozen", "id": jid,
                            "reason": "pending job has no trigger in the queue"})
        return _execute(root, state, match, token, resumed=True, inject=args.inject,
                        lease_expired=lease_expired)

    if next_seq not in by_seq:
        ahead = sorted(s for s in by_seq if s > next_seq)
        if ahead:
            # 严格 FIFO：不跳过缺口，等待缺失的序号到达。
            raise Rejected({"action": "out-of-order-rejected",
                            "expected_seq": next_seq,
                            "missing_seq": next_seq,
                            "reason": "no trigger at the cursor; strict FIFO policy",
                            "next_available_seq": ahead[0]})
        late = [t for t in unique
                if t["seq"] <= state["cursor_seq"] and t["id"] not in state["consumed"]]
        if late:
            raise Rejected({"action": "conflict-frozen", "id": sorted(late, key=lambda t: t["seq"])[0]["id"],
                            "reason": "trigger below the cursor was never consumed",
                            "cursor_seq": state["cursor_seq"]})
        emit({"action": "no-work", "cursor_seq": state["cursor_seq"],
              "note": "queue holds no unconsumed trigger"})
        return EXIT_OK
    trigger = by_seq[next_seq]
    if trigger["id"] in state["consumed"]:
        emit({"action": "duplicate-noop", "id": trigger["id"],
              "note": "trigger already consumed exactly once"})
        return EXIT_OK
    return _execute(root, state, trigger, token, resumed=False, inject=args.inject,
                    lease_expired=lease_expired)


def _execute(root, state, trigger, token, resumed, inject, lease_expired=False):
    jid = trigger["id"]
    target = trigger["target_bot"]
    version = trigger["candidate_version"]
    job = state["jobs"].get(jid) or {
        "status": "APPLY_PENDING", "reason": None, "seq": trigger["seq"],
        "target_bot": target, "candidate_version": version,
        "before_sha256": None, "before_present": None, "after_sha256": None,
        "lease_token": token, "updated_at": now_iso(),
        "candidate_sha256": None, "aborted": False,
    }
    recorded_lease = job.get("lease_token")
    if recorded_lease is not None and recorded_lease != token:
        # 租约世代推进了。只有「旧租约已过期、作业因此被接管」是合法的续作；
        # 旧租约仍然活着时，当前调用者无权替别人续作。
        # （活着的他人租约在进入这里之前就已经被 lease-held 挡下，
        #   所以这一分支是纵深防御：防止将来改动流程时把 fencing 拆掉。）
        if not lease_expired:
            job["status"] = "APPLY_PENDING"
            job["reason"] = "stale-lease"
            job["updated_at"] = now_iso()
            state["jobs"][jid] = job
            save_state(root, state)
            audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                         "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                         "reason": "stale-lease", "recorded_lease_token": recorded_lease,
                         "current_lease_token": token})
            raise Rejected({"action": "stale-lease", "id": jid, "result": "APPLY_PENDING",
                            "recorded_lease_token": recorded_lease,
                            "current_lease_token": token})
        # 旧租约已过期：接管续作，记录新的租约世代。
        audit(root, {"ts": now_iso(), "action": "lease-resumed-after-expiry",
                     "trigger_id": jid, "seq": trigger["seq"], "target_bot": target,
                     "result": "RESUMED", "recorded_lease_token": recorded_lease,
                     "current_lease_token": token})
    job["seq"] = trigger["seq"]
    job["target_bot"] = target
    job["candidate_version"] = version
    job["lease_token"] = token
    job.setdefault("aborted", False)

    if state["kill_switch"]["engaged"]:
        job["status"] = "APPLY_PENDING"
        job["reason"] = "kill-switch-engaged"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "kill-switch-engaged", "lease_token": token})
        raise Rejected({"action": "kill-switch-engaged", "id": jid, "result": "APPLY_PENDING"})

    # 崩溃恢复窗口：原子替换（rename）已经落地，但进程在写状态之前中断。
    # 此时平台字节等于「当时批准的候选字节」——不能当成「别人改了目标」而拒绝
    # （那会把游标永久卡死），也不能再应用一次；应当读回确认并补齐状态。
    recorded_digest = job.get("candidate_sha256")
    if job.get("status") == "APPLY_PENDING" and recorded_digest:
        approval = state["approvals"].get(version)
        if approval and approval["candidate_sha256"] == recorded_digest \
                and platform_digest(root, target) == recorded_digest:
            return _complete_apply(root, state, trigger, job, token, resumed=True,
                                   digest=recorded_digest,
                                   before_digest=job.get("before_sha256"),
                                   others=sorted(b for b in expected_state(state)
                                                 if b != target),
                                   recovered=True)

    raw, cand = load_candidate(root, version)
    digest = sha256_hex(raw)

    approval = state["approvals"].get(version)
    if not approval:
        job["status"] = "APPLY_PENDING"
        job["reason"] = "approval-missing"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "approval-missing", "lease_token": token})
        raise Rejected({"action": "approval-missing", "id": jid, "result": "APPLY_PENDING"})

    if digest != approval["candidate_sha256"]:
        job["status"] = "APPLY_PENDING"
        job["reason"] = "stale-candidate"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "stale-candidate", "candidate_sha256": digest,
                     "approved_sha256": approval["candidate_sha256"], "lease_token": token})
        raise Rejected({"action": "stale-candidate", "id": jid, "result": "APPLY_PENDING",
                        "candidate_sha256": digest,
                        "approved_sha256": approval["candidate_sha256"]})
    if cand["bot"] != target:
        raise ContractError("candidate %s: bot %r does not match target_bot %r"
                            % (version, cand["bot"], target))

    baseline = state["platform_baseline"]
    if not baseline:
        job["status"] = "APPLY_PENDING"
        job["reason"] = "baseline-missing"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "baseline-missing", "lease_token": token})
        raise Rejected({"action": "baseline-missing", "id": jid, "result": "APPLY_PENDING"})

    expected = expected_state(state)
    others = sorted(b for b in expected if b != target)
    drifted = []
    for bot in others:
        current = platform_digest(root, bot)
        if current != expected[bot]:
            drifted.append(bot)
    known_bots = platform_bots(root)
    unknown = [b for b in known_bots if b not in baseline and b != target]
    # 目标本身不在基线内时，应用前拒绝，并且不创建、不覆盖平台文件。
    # 文件尚不存在时 platform_digest 与 expected.get 都是 None，后面的漂移
    # 比较会把「可以新建」当成「没有漂移」，写出基线外的 Bot；verify 随后
    # 因 baseline 外 Bot 失败，后面的序号也被挡住。
    if target not in baseline:
        unknown_targets = sorted(set(unknown + [target]))
        job["status"] = "APPLY_PENDING"
        job["reason"] = "other-bot-changed"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "other-bot-changed", "drifted_bots": drifted,
                     "unknown_bots": unknown_targets, "lease_token": token,
                     "detail": "target bot is not in the baseline"})
        raise Rejected({"action": "other-bot-changed", "id": jid, "result": "APPLY_PENDING",
                        "drifted_bots": drifted, "unknown_bots": unknown_targets})
    target_current = platform_digest(root, target)
    if target_current != expected.get(target):
        job["status"] = "APPLY_PENDING"
        job["reason"] = "conflict-frozen"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "conflict-frozen",
                     "detail": "target bot drifted from the expected state",
                     "expected_sha256": expected.get(target),
                     "current_sha256": target_current, "lease_token": token})
        raise Rejected({"action": "conflict-frozen", "id": jid, "result": "APPLY_PENDING",
                        "expected_sha256": expected.get(target),
                        "current_sha256": target_current})
    if drifted or unknown:
        job["status"] = "APPLY_PENDING"
        job["reason"] = "other-bot-changed"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "other-bot-changed", "drifted_bots": drifted,
                     "unknown_bots": unknown, "lease_token": token})
        raise Rejected({"action": "other-bot-changed", "id": jid, "result": "APPLY_PENDING",
                        "drifted_bots": drifted, "unknown_bots": unknown})

    target_file = platform_path(root, target)
    before_present = target_file.exists()
    before_bytes = read_file_bytes(target_file, "platform %s" % target, MAX_PLATFORM_BYTES) \
        if before_present else b""
    before_digest = sha256_hex(before_bytes) if before_present else None

    if job.get("before_sha256") is not None or job.get("before_present") is not None:
        # 续作：之前记录过应用前状态，当前字节必须仍与记录一致。
        current = platform_digest(root, target)
        recorded = job.get("before_sha256")
        if current != recorded:
            job["status"] = "APPLY_PENDING"
            job["reason"] = "conflict-frozen"
            job["updated_at"] = now_iso()
            state["jobs"][jid] = job
            save_state(root, state)
            audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                         "seq": trigger["seq"], "target_bot": target,
                         "result": "APPLY_PENDING", "reason": "conflict-frozen",
                         "detail": "target bot drifted since the recorded before-state",
                         "recorded_sha256": recorded, "current_sha256": current,
                         "lease_token": token})
            raise Rejected({"action": "conflict-frozen", "id": jid, "result": "APPLY_PENDING",
                            "recorded_sha256": recorded, "current_sha256": current})
    else:
        job["before_sha256"] = before_digest
        job["before_present"] = before_present
        write_atomic(root / "backups" / ("%s.json" % jid), before_bytes)

    # 在原子替换之前把「将要写入的候选字节摘要」记进作业台账。
    # 这样即使进程在 rename 之后、写状态之前崩溃，下一次 trigger 也能靠这个
    # 摘要认出「替换已经落地」，而不是把目标当成被外人改动而永久卡死游标。
    job["candidate_sha256"] = digest
    state["jobs"][jid] = job
    save_state(root, state)

    if inject == "APPLY":
        # 模拟在原子替换前崩溃：候选字节只落到临时文件，平台文件未被替换，
        # 状态留在 APPLY_PENDING，等下一次 trigger 续作。
        tmp = target_file.parent / ("." + target_file.name + ".durable-trigger.partial")
        tmp_bytes = raw
        tmp_fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(tmp_fd, tmp_bytes)
            os.fsync(tmp_fd)
        finally:
            os.close(tmp_fd)
        job["status"] = "APPLY_PENDING"
        job["reason"] = "injected-failure-at-apply"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "injected-failure-at-apply", "lease_token": token})
        raise Rejected({"action": "apply-failed", "id": jid, "result": "APPLY_PENDING",
                        "reason": "injected-failure-at-apply"})

    write_atomic(target_file, raw)

    if inject == "READBACK":
        # 模拟平台侧字节与已批准候选不一致：读回必须发现差异并回退。
        write_atomic(target_file, b'{"bot":"' + target.encode("utf-8")
                     + b'","stage":0,"config":{"truncated":true}}\n')

    if inject == "OTHER_BOT":
        victim = others[0] if others else None
        if victim:
            write_atomic(platform_path(root, victim), b'{"bot":"' + victim.encode("utf-8")
                         + b'","stage":9,"config":{"tampered":true}}\n')

    readback = platform_digest(root, target)
    if readback != digest:
        _restore(root, target, job, jid)
        job["status"] = "APPLY_PENDING"
        job["reason"] = "readback-mismatch"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "readback-mismatch", "expected_sha256": digest,
                     "readback_sha256": readback, "lease_token": token})
        raise Rejected({"action": "readback-mismatch", "id": jid, "result": "APPLY_PENDING",
                        "expected_sha256": digest, "readback_sha256": readback})

    post_expected = expected_state(state)
    post_drifted = []
    for bot in sorted(post_expected):
        if bot == target:
            continue
        if platform_digest(root, bot) != post_expected[bot]:
            post_drifted.append(bot)
    if post_drifted:
        _restore(root, target, job, jid)
        job["status"] = "APPLY_PENDING"
        job["reason"] = "other-bot-changed"
        job["updated_at"] = now_iso()
        state["jobs"][jid] = job
        save_state(root, state)
        audit(root, {"ts": now_iso(), "action": "apply-refused", "trigger_id": jid,
                     "seq": trigger["seq"], "target_bot": target, "result": "APPLY_PENDING",
                     "reason": "other-bot-changed", "drifted_bots": post_drifted,
                     "lease_token": token})
        raise Rejected({"action": "other-bot-changed", "id": jid, "result": "APPLY_PENDING",
                        "drifted_bots": post_drifted})

    return _complete_apply(root, state, trigger, job, token, resumed=resumed,
                           digest=digest, before_digest=before_digest,
                           others=others)


def _complete_apply(root, state, trigger, job, token, resumed, digest, before_digest,
                    others, recovered=False):
    """把一次成功读回的应用落账：标 APPLIED、推进游标、写审计。"""
    jid = trigger["id"]
    target = trigger["target_bot"]
    version = trigger["candidate_version"]
    readback = platform_digest(root, target)
    job["status"] = "APPLIED"
    job["reason"] = None
    job["after_sha256"] = digest
    job["updated_at"] = now_iso()
    state["jobs"][jid] = job
    state["consumed"][jid] = {"seq": trigger["seq"], "result": "APPLIED", "at": now_iso()}
    state["cursor_seq"] = trigger["seq"]
    save_state(root, state)
    audit(root, {"ts": now_iso(), "action": "applied", "trigger_id": jid,
                 "seq": trigger["seq"], "target_bot": target, "candidate_version": version,
                 "result": "APPLIED", "before_sha256": before_digest,
                 "after_sha256": digest, "readback_sha256": readback,
                 "other_bots_unchanged": True, "other_bots": others,
                 "resumed": resumed, "recovered_after_crash": recovered,
                 "lease_token": token})
    emit({"action": "applied", "id": jid, "seq": trigger["seq"], "target_bot": target,
          "candidate_version": version, "before_sha256": before_digest,
          "after_sha256": digest, "readback_sha256": readback,
          "other_bots_unchanged": True, "other_bots": others, "resumed": resumed,
          "recovered_after_crash": recovered,
          "cursor_seq": state["cursor_seq"], "lease_token": token})
    return EXIT_OK


def _restore(root, target, job, jid):
    """把目标 Bot 的平台文件原子恢复到应用前字节。"""
    path = platform_path(root, target)
    if job.get("before_present"):
        backup = root / "backups" / ("%s.json" % jid)
        data = read_file_bytes(backup, "backup", MAX_PLATFORM_BYTES)
        write_atomic(path, data)
    else:
        try:
            path.unlink()
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise
        fsync_dir(path.parent)


def cmd_abort(args):
    """把一个卡住的 APPLY_PENDING 作业标记为 ABORTED，让游标能继续往前走。

    这是「租约过期后作业无人续作」的最后一道人工出口：没有它，一个失败的
    作业会把游标永久钉在它那一格，后面所有触发都出不来。
    """
    root = Path(args.root).resolve()
    ensure_layout(root)
    with_lock(root, lambda: _abort_locked(root, args))
    return EXIT_OK


def _abort_locked(root, args):
    state = load_state(root)
    jid = args.trigger_id
    job = state["jobs"].get(jid)
    if not job:
        raise Rejected({"action": "abort-unavailable", "id": jid,
                        "reason": "no such job"})
    if job.get("status") == "ABORTED":
        emit({"action": "already-aborted", "id": jid})
        return EXIT_OK
    if job.get("status") != "APPLY_PENDING":
        raise Rejected({"action": "abort-unavailable", "id": jid,
                        "reason": "job is not pending", "status": job.get("status")})
    target = job.get("target_bot")
    seq = job.get("seq")
    # 中止只解除「这一格被卡住」的占位，不动平台字节：
    # 目标若仍等于应用前字节，说明什么都没写进去，无需回滚。
    current = platform_digest(root, target) if target else None
    if current is not None and current == job.get("before_sha256"):
        restored = False
    else:
        _restore(root, target, job, jid)
        restored = True
    job["status"] = "ABORTED"
    job["reason"] = args.reason or "aborted-by-operator"
    job["aborted"] = True
    job["updated_at"] = now_iso()
    state["jobs"][jid] = job
    state["consumed"][jid] = {"seq": seq, "result": "ABORTED", "at": now_iso()}
    if isinstance(seq, int) and seq > state["cursor_seq"]:
        state["cursor_seq"] = seq
    save_state(root, state)
    audit(root, {"ts": now_iso(), "action": "aborted", "trigger_id": jid,
                 "seq": seq, "target_bot": target, "result": "ABORTED",
                 "reason": job["reason"], "platform_restored": restored,
                 "holder": args.holder})
    emit({"action": "aborted", "id": jid, "seq": seq, "target_bot": target,
          "platform_restored": restored, "cursor_seq": state["cursor_seq"]})
    return EXIT_OK


def cmd_rollback(args):
    root = Path(args.root).resolve()
    ensure_layout(root)
    with_lock(root, lambda: _rollback_locked(root, args))
    return EXIT_OK


def _rollback_locked(root, args):
    state = load_state(root)
    jid = args.trigger_id
    job = state["jobs"].get(jid)
    if not job:
        raise Rejected({"action": "rollback-unavailable", "id": jid,
                        "reason": "no such job"})
    if job.get("status") == "ROLLED_BACK":
        emit({"action": "already-rolled-back", "id": jid})
        return EXIT_OK
    if job.get("status") != "APPLIED":
        raise Rejected({"action": "rollback-unavailable", "id": jid,
                        "reason": "job was never applied", "status": job.get("status")})
    target = job["target_bot"]
    backup = root / "backups" / ("%s.json" % jid)
    if job.get("before_present"):
        data = read_file_bytes(backup, "backup", MAX_PLATFORM_BYTES)
        write_atomic(platform_path(root, target), data)
        restored = platform_digest(root, target)
        if restored != job.get("before_sha256"):
            raise Rejected({"action": "rollback-failed", "id": jid,
                            "expected_sha256": job.get("before_sha256"),
                            "readback_sha256": restored})
    else:
        path = platform_path(root, target)
        try:
            path.unlink()
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise
        fsync_dir(path.parent)
        restored = None
    job["status"] = "ROLLED_BACK"
    job["reason"] = None
    job["updated_at"] = now_iso()
    state["jobs"][jid] = job
    save_state(root, state)
    audit(root, {"ts": now_iso(), "action": "rolled-back", "trigger_id": jid,
                 "target_bot": target, "result": "ROLLED_BACK",
                 "restored_sha256": restored, "holder": args.holder})
    emit({"action": "rolled-back", "id": jid, "target_bot": target,
          "restored_sha256": restored})
    return EXIT_OK


def cmd_kill_switch(args):
    root = Path(args.root).resolve()
    ensure_layout(root)
    with_lock(root, lambda: _kill_switch_locked(root, args))
    return EXIT_OK


def _kill_switch_locked(root, args):
    state = load_state(root)
    if args.engage:
        state["kill_switch"] = {"engaged": True, "reason": args.reason, "at": now_iso()}
        action = "kill-switch-engaged"
    else:
        state["kill_switch"] = {"engaged": False, "reason": None, "at": now_iso()}
        action = "kill-switch-released"
    save_state(root, state)
    audit(root, {"ts": now_iso(), "action": action, "reason": args.reason})
    emit({"action": action, "engaged": state["kill_switch"]["engaged"]})
    return EXIT_OK


def cmd_status(args):
    root = Path(args.root).resolve()
    state = load_state(root)
    emit({
        "action": "status",
        "schema_version": state["schema_version"],
        "cursor_seq": state["cursor_seq"],
        "lease": state["lease"],
        "kill_switch": state["kill_switch"],
        "platform_baseline": state["platform_baseline"],
        "approvals": state["approvals"],
        "jobs": state["jobs"],
        "consumed": state["consumed"],
    })
    return EXIT_OK


def cmd_verify(args):
    root = Path(args.root).resolve()
    state = load_state(root)
    problems = []
    triggers = load_queue(root)
    ids = [t["id"] for t in triggers]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        problems.append("queue contains duplicate ids: %s" % ",".join(duplicated))
    for jid in state["consumed"]:
        if jid not in state["jobs"]:
            problems.append("consumed trigger %s has no job record" % jid)
    for jid, job in state["jobs"].items():
        if job.get("status") == "APPLIED" and not job.get("after_sha256"):
            problems.append("job %s is APPLIED without after_sha256" % jid)
    # 卡死的游标：一个 APPLY_PENDING 作业坐在游标位上，却已经没有任何在世
    # 的租约可以续作它 —— 这就是「租约过期后无人接管」的死锁，必须报出来。
    if state["lease"]["holder"] is None or \
            state["lease"]["expires_at"] <= time.time():
        stuck = sorted(
            (jid for jid, job in state["jobs"].items()
             if job.get("status") == "APPLY_PENDING"
             and job.get("seq") == state["cursor_seq"] + 1),
            key=lambda jid: jid)
        for jid in stuck:
            problems.append("job %s is pending at the cursor with no live lease to resume it"
                            % jid)
    expected = expected_state(state)
    current = {}
    for bot in platform_bots(root):
        current[bot] = platform_digest(root, bot)
    changed = sorted(b for b in expected if current.get(b) != expected[b])
    unknown = sorted(b for b in current if b not in state["platform_baseline"])
    missing = sorted(b for b in state["platform_baseline"] if b not in current)
    if changed:
        problems.append("platform differs from expected state for: %s" % ",".join(changed))
    if unknown:
        problems.append("platform has bots outside the baseline: %s" % ",".join(unknown))
    if missing:
        problems.append("platform is missing baselined bots: %s" % ",".join(missing))
    # 审计编码/schema 错误走契约错误（exit 2），与队列同一条路径。
    # 不收成 verify FAIL：退出码表把编码错误定为 2，未捕获的 UnicodeDecodeError
    # 也不能冒充成一次有 verdict 的校验。
    entries = load_audit(root)
    if problems:
        emit({"verdict": "FAIL", "scope": "state-queue-platform-audit-bytes-only",
              "problems": problems, "cursor_seq": state["cursor_seq"],
              "audit_entries": len(entries)})
        return EXIT_REJECTED
    emit({"verdict": "PASS", "scope": "state-queue-platform-audit-bytes-only",
          "cursor_seq": state["cursor_seq"], "queue_triggers": len(triggers),
          "jobs": len(state["jobs"]), "audit_entries": len(entries),
          "platform": current})
    return EXIT_OK


def cmd_version(_args):
    readme = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
    print("%s %s" % (VERSION, sha256_hex(open(readme, "rb").read())))
    return EXIT_OK


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog="durable_trigger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    eq = sub.add_parser("enqueue")
    eq.add_argument("--root", required=True)
    eq.add_argument("--trigger", required=True)
    eq.set_defaults(func=cmd_enqueue)

    ap = sub.add_parser("approve")
    ap.add_argument("--root", required=True)
    ap.add_argument("--candidate-version", required=True)
    ap.add_argument("--approver", required=True)
    ap.set_defaults(func=cmd_approve)

    bl = sub.add_parser("baseline")
    bl.add_argument("--root", required=True)
    bl.set_defaults(func=cmd_baseline)

    tr = sub.add_parser("trigger")
    tr.add_argument("--root", required=True)
    tr.add_argument("--holder", required=True)
    tr.add_argument("--lease-seconds", type=float, default=60.0)
    tr.add_argument("--lease-token", type=int, default=None)
    tr.add_argument("--inject-failure", dest="inject", choices=INJECT_POINTS, default=None)
    tr.set_defaults(func=cmd_trigger)

    ab = sub.add_parser("abort")
    ab.add_argument("--root", required=True)
    ab.add_argument("--trigger-id", required=True)
    ab.add_argument("--holder", default="operator")
    ab.add_argument("--reason", default=None)
    ab.set_defaults(func=cmd_abort)

    rb = sub.add_parser("rollback")
    rb.add_argument("--root", required=True)
    rb.add_argument("--trigger-id", required=True)
    rb.add_argument("--holder", default="operator")
    rb.set_defaults(func=cmd_rollback)

    ks = sub.add_parser("kill-switch")
    ks.add_argument("--root", required=True)
    group = ks.add_mutually_exclusive_group(required=True)
    group.add_argument("--engage", action="store_true")
    group.add_argument("--release", action="store_true")
    ks.add_argument("--reason", default=None)
    ks.set_defaults(func=cmd_kill_switch)

    st = sub.add_parser("status")
    st.add_argument("--root", required=True)
    st.set_defaults(func=cmd_status)

    vf = sub.add_parser("verify")
    vf.add_argument("--root", required=True)
    vf.set_defaults(func=cmd_verify)

    vs = sub.add_parser("--version", add_help=False)
    vs.set_defaults(func=cmd_version)
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--version"]:
        return cmd_version(None)
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Rejected as exc:
        emit(exc.payload)
        return EXIT_REJECTED
    except ContractError as exc:
        print("contract error: %s" % exc, file=sys.stderr)
        return EXIT_CONTRACT
    except OSError as exc:
        print("io error: %s" % exc, file=sys.stderr)
        return EXIT_CONTRACT


if __name__ == "__main__":
    sys.exit(main())
