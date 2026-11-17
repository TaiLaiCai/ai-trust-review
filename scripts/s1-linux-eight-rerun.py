#!/usr/bin/env python3
"""Fixed eight-step inspect / rerun helper for one frozen ZIP.

Default mode reads and reports. It does not execute an archive.
This is schema s1-linux-eight-rerun/v0, not rerun-receipt/v1: there is no
git HEAD binding, argv is not taken from a manifest, and S1 stays NOT_TESTED.

The process table is not a sandbox. OS mounts, SSH forced-command, key
lifetime, and VM destruction are not implemented here.
"""
import argparse
import dataclasses
import datetime
import errno
import hashlib
import io
import json
import os
import random
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

SCHEMA = "s1-linux-eight-rerun/v0"
BINDING_SCHEMA = "s1-linux-eight-binding/v0"
WHY_NOT_V1 = "no-git-head-binding"

MAX_ZIP_BYTES = 1024 * 1024
MAX_ENTRIES = 64
MAX_MEMBER_BYTES = 256 * 1024
MAX_TOTAL_UNCOMPRESSED = 1024 * 1024
RATIO_FLOOR = 64 * 1024
MAX_RATIO = 80
MAX_BINDING_BYTES = 64 * 1024
MAX_NAME_CHARS = 256
DEFAULT_TIMEOUT_SECONDS = 30
MAX_STREAM_BYTES = 1024 * 1024
CHILD_PATH = "/usr/bin:/bin"

HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,128}")
FIXTURE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")
ENTRY_MEMBERS = (
    "README.md",
    "preflight.py",
    "sample_fixed.json",
    "status_input.json",
    "status_tool.py",
    "test_preflight.py",
    "test_status_tool.py",
)
STDIN_SIZES = {"T4": 2, "T5": 8, "T6": 19}
STEP_IDS = ("T1", "T2", "T3", "T4", "T5", "T6", "TP", "PREFLIGHT-LOCAL")
BINDING_TOP_KEYS = frozenset({"schema_version", "steps", "members", "stdin_fixtures"})
FIXTURE_KEYS = frozenset({"bytes", "sha256", "name"})


@dataclasses.dataclass(frozen=True)
class ArchiveIdentity:
    sha256: str
    nbytes: int
    regular_files: int
    uncompressed_bytes: int


@dataclasses.dataclass(frozen=True)
class Step:
    id: str
    argv: tuple
    stdin_kind: str | None
    map_expected_exit: int
    historical_other_exit: int | None = None
    stdout_same_as: str | None = None


# Published freeze supplied with this task. Member digests are not included.
FROZEN = ArchiveIdentity(
    sha256="551123d9dd8eb8f3e05f0dc2ad8c69207c95db2a19cf524f50988691055538f1",
    nbytes=42705,
    regular_files=18,
    uncompressed_bytes=95203,
)

STEP_TABLE = (
    Step("T1", ("python3", "-m", "unittest", "test_status_tool", "-v"), None, 0),
    Step("T2", ("python3", "status_tool.py", "--file", "status_input.json"), None, 0),
    Step("T3", ("python3", "status_tool.py"), "status_input", 0, stdout_same_as="T2"),
    Step("T4", ("python3", "status_tool.py"), "T4", 0),
    Step("T5", ("python3", "status_tool.py"), "T5", 2),
    Step("T6", ("python3", "status_tool.py"), "T6", 2),
    Step("TP", ("python3", "-m", "unittest", "test_preflight", "-v"), None, 0),
    Step("PREFLIGHT-LOCAL", ("python3", "preflight.py"), None, 0, historical_other_exit=3),
)


class Problem(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class Measured:
    def __init__(self, public, bodies):
        self.public = public
        self.bodies = bodies


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def tool_file_sha256():
    with open(__file__, "rb") as stream:
        return sha256_bytes(stream.read())


def dumps(obj):
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Problem("binding-invalid")
        result[key] = value
    return result


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def identity_public(identity):
    return {
        "bytes": identity.nbytes,
        "regular_files": identity.regular_files,
        "sha256": identity.sha256,
        "uncompressed_bytes": identity.uncompressed_bytes,
    }


def empty_archive():
    return {
        "bytes": None,
        "identity": "unmeasured",
        "layout": None,
        "regular_files": None,
        "safety": "unmeasured",
        "safety_reasons": [],
        "sha256": None,
        "source_unchanged": None,
        "uncompressed_bytes": None,
    }


def base_receipt(mode):
    return {
        "archive": empty_archive(),
        "binding_problems": [],
        "binding_status": "absent",
        "executed": False,
        "hour_limit_24": "NOT_IMPLEMENTED",
        "isolation": {
            "filesystem_limited_by_this_tool": False,
            "network_limited_by_this_tool": False,
            "os_ssh_forced_command": "NOT_IMPLEMENTED",
            "subprocess_is_sandbox": False,
        },
        "lifecycle_vm_key_destruction": "NOT_IMPLEMENTED",
        "members": [],
        "content_expectation": "NOT_PROVIDED",
        "mode": mode,
        "not_rerun_receipt_v1": True,
        "preflight_historical_conflict": "UNRESOLVED",
        "preflight_normalized_to_pass": False,
        "pycache_entries": None,
        "reason": None,
        "required_identity": identity_public(FROZEN),
        "s1_judgment": "NOT_TESTED",
        "schema_version": SCHEMA,
        "scratch": "not-created",
        "steps": [step_shell(spec) for spec in STEP_TABLE],
        "technical_status": "refused",
        "tool_exit_meaning": "technical-only",
        "tool_file_sha256": None,
        "why_not_rerun_receipt_v1": WHY_NOT_V1,
    }


def step_shell(spec):
    return {
        "actual_vs_map": "not-compared",
        "exit_code": None,
        "finished_at": None,
        "historical_conflict": "UNRESOLVED" if spec.historical_other_exit is not None else None,
        "historical_other_exit": spec.historical_other_exit,
        "id": spec.id,
        "map_expected_exit": spec.map_expected_exit,
        "normalized_to_pass": False,
        "s1_step_judgment": "NOT_TESTED",
        "started_at": None,
        "stderr_bytes": None,
        "stderr_sha256": None,
        "stderr_truncated": False,
        "stdin_bytes": None,
        "stdin_sha256": None,
        "stdout_bytes": None,
        "stdout_relation": "not-compared" if spec.stdout_same_as else None,
        "stdout_same_as": spec.stdout_same_as,
        "stdout_sha256": None,
        "stdout_truncated": False,
        "technical_status": "not-run",
    }


def classify(info):
    name = info.filename
    if not isinstance(name, str) or len(name) > MAX_NAME_CHARS or "\x00" in name or "\\" in name:
        return "path-escape"
    if name.startswith("/") or name.startswith("~"):
        return "path-escape"
    raw = name[:-1] if name.endswith("/") else name
    if not raw:
        return "path-escape"
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "path-escape"
    if re.match(r"^[A-Za-z]:", raw):
        return "path-escape"
    mode = info.external_attr >> 16
    fmt = stat.S_IFMT(mode)
    if fmt == stat.S_IFLNK:
        return "symlink"
    if fmt in (stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK):
        return "special-file"
    if fmt not in (0, stat.S_IFREG, stat.S_IFDIR):
        return "special-file"
    if name.endswith("/") or info.is_dir() or fmt == stat.S_IFDIR:
        return "dir"
    return "regular"


def measure(data):
    public = {
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "safety": "clear",
        "safety_reasons": [],
        "regular_files": 0,
        "uncompressed_bytes": 0,
        "layout": "flat",
        "members": [],
    }
    if len(data) > MAX_ZIP_BYTES:
        public["safety"] = "unsafe"
        public["safety_reasons"] = ["zip-too-large"]
        public["layout"] = None
        return Measured(public, {})
    reasons = []
    members = []
    bodies = {}
    total = 0
    nested = False
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        public["safety"] = "unsafe"
        public["safety_reasons"] = ["bad-zip"]
        public["layout"] = None
        return Measured(public, {})
    try:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            public["safety"] = "unsafe"
            public["safety_reasons"] = ["too-many-members"]
            public["layout"] = None
            return Measured(public, {})
        seen = set()
        for info in infos:
            name = info.filename if isinstance(info.filename, str) else ""
            if name in seen:
                reasons.append("duplicate-path")
                continue
            seen.add(name)
            kind = classify(info)
            if kind in ("path-escape", "symlink", "special-file"):
                reasons.append(kind)
                continue
            if kind == "dir":
                members.append({"bytes": 0, "kind": "dir", "path": name, "sha256": None})
                continue
            if info.flag_bits & 0x1:
                reasons.append("encrypted")
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                reasons.append("member-too-large")
                continue
            if info.file_size >= RATIO_FLOOR:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_RATIO:
                    reasons.append("compression-ratio")
                    continue
            total += info.file_size
            if total > MAX_TOTAL_UNCOMPRESSED:
                reasons.append("total-too-large")
                continue
            try:
                with archive.open(info, "r") as stream:
                    blob = stream.read(info.file_size + 1)
            except RuntimeError:
                reasons.append("encrypted")
                continue
            except zipfile.BadZipFile:
                reasons.append("bad-zip")
                continue
            if len(blob) != info.file_size:
                reasons.append("declared-size-mismatch")
                continue
            if "/" in name:
                nested = True
            digest = sha256_bytes(blob)
            members.append({
                "bytes": len(blob),
                "kind": "regular",
                "path": name,
                "sha256": digest,
            })
            if "/" not in name and SAFE_NAME.fullmatch(name):
                bodies[name] = blob
            elif "/" not in name:
                reasons.append("member-name")
    finally:
        archive.close()
    if reasons:
        public["safety"] = "unsafe"
        public["safety_reasons"] = sorted(set(reasons))
        public["members"] = []
        public["regular_files"] = 0
        public["uncompressed_bytes"] = 0
        public["layout"] = None
        return Measured(public, {})
    public["members"] = members
    public["regular_files"] = sum(1 for item in members if item["kind"] == "regular")
    public["uncompressed_bytes"] = sum(item["bytes"] for item in members if item["kind"] == "regular")
    public["layout"] = "nested" if nested else "flat"
    if nested:
        bodies = {}
    return Measured(public, bodies)


def compare_identity(public, identity):
    sha_match = public["sha256"] == identity.sha256 and public["bytes"] == identity.nbytes
    if public["safety"] != "clear":
        return "census-conflict" if sha_match else "mismatch"
    if not sha_match:
        return "mismatch"
    census_match = (
        public["regular_files"] == identity.regular_files
        and public["uncompressed_bytes"] == identity.uncompressed_bytes
    )
    return "match" if census_match else "census-conflict"


def load_binding(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise Problem("binding-invalid") from None
        raise Problem("binding-invalid") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BINDING_BYTES:
            raise Problem("binding-invalid")
        raw = os.read(fd, MAX_BINDING_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_BINDING_BYTES:
        raise Problem("binding-invalid")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, Problem):
        raise Problem("binding-invalid") from None
    if not isinstance(obj, dict) or set(obj) != BINDING_TOP_KEYS:
        raise Problem("binding-invalid")
    if obj["schema_version"] != BINDING_SCHEMA:
        raise Problem("binding-invalid")
    if obj["steps"] != list(STEP_IDS):
        raise Problem("binding-invalid")
    members = obj["members"]
    if not isinstance(members, dict) or not members:
        raise Problem("binding-invalid")
    clean_members = {}
    for name, digest in members.items():
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
            raise Problem("binding-invalid")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise Problem("binding-invalid")
        clean_members[name] = digest
    fixtures = obj["stdin_fixtures"]
    if not isinstance(fixtures, dict) or set(fixtures) != set(STDIN_SIZES):
        raise Problem("binding-invalid")
    clean_fixtures = {}
    for step_id, rule_bytes in STDIN_SIZES.items():
        item = fixtures[step_id]
        if not isinstance(item, dict) or set(item) != FIXTURE_KEYS:
            raise Problem("binding-invalid")
        if not is_int(item["bytes"]) or item["bytes"] != rule_bytes:
            raise Problem("binding-invalid")
        if not isinstance(item["sha256"], str) or not HEX64.fullmatch(item["sha256"]):
            raise Problem("binding-invalid")
        if not isinstance(item["name"], str) or not FIXTURE_NAME.fullmatch(item["name"]):
            raise Problem("binding-invalid")
        clean_fixtures[step_id] = {
            "bytes": item["bytes"],
            "name": item["name"],
            "sha256": item["sha256"],
        }
    return {"members": clean_members, "stdin_fixtures": clean_fixtures}


def assess_binding(measured, binding):
    problems = []
    regular = {
        item["path"]: item
        for item in measured.public["members"]
        if item["kind"] == "regular"
    }
    for name in ENTRY_MEMBERS:
        if name not in regular:
            problems.append("missing-entry:" + name)
    for path in regular:
        pinned = binding["members"].get(path)
        if pinned is None:
            problems.append("unpinned:" + path)
        elif pinned != regular[path]["sha256"]:
            problems.append("sha-mismatch:" + path)
    for path in binding["members"]:
        if path not in regular:
            problems.append("extra-member:" + path)
    if any(item.startswith("sha-mismatch:") for item in problems):
        status = "sha-mismatch"
    elif problems:
        status = "incomplete"
    else:
        status = "complete"
    return status, problems


def read_fixture(dir_path, name, expect_len):
    if not FIXTURE_NAME.fullmatch(name):
        raise Problem("fixture-unreadable")
    try:
        dir_fd = os.open(dir_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise Problem("fixture-unreadable") from None
        raise Problem("fixture-unreadable") from None
    try:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise Problem("fixture-unreadable") from None
            raise Problem("fixture-unreadable") from None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise Problem("fixture-unreadable")
            if st.st_size != expect_len:
                raise Problem("fixture-length")
            data = os.read(fd, expect_len + 1)
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)
    if len(data) != expect_len:
        raise Problem("fixture-length")
    return data


def output_dir_fd(zip_path, output_dir):
    out = os.path.abspath(output_dir)
    source_parent = os.path.realpath(os.path.dirname(os.fspath(zip_path)) or ".")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = None
    try:
        fd = os.open(os.sep, flags)
        for part in filter(None, out.split(os.sep)):
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        if os.path.commonpath((out, source_parent)) == source_parent:
            raise Problem("output-dir-overlaps-source")
        opened, fd = fd, None
        return opened
    except OSError:
        raise Problem("output-dir-unsafe") from None
    finally:
        if fd is not None:
            os.close(fd)


def read_zip(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        fd = os.open(path, flags)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise Problem("zip-is-symlink") from None
        raise Problem("unreadable-zip") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Problem("not-regular-file")
        if st.st_size > MAX_ZIP_BYTES:
            raise Problem("zip-too-large")
        data = os.read(fd, MAX_ZIP_BYTES + 1)
        if len(data) > MAX_ZIP_BYTES:
            raise Problem("zip-too-large")
        st2 = os.fstat(fd)
        if st2.st_size != st.st_size or st2.st_mtime_ns != st.st_mtime_ns:
            raise Problem("source-changed")
        mode = stat.S_IMODE(st.st_mode)
        return data, mode
    finally:
        os.close(fd)


def confirm_source(path, data, mode):
    try:
        again, mode2 = read_zip(path)
    except Problem:
        return False
    return again == data and mode2 == mode


def write_receipt(dir_fd, text):
    """Write a new inode, then replace the receipt name.

    O_TRUNC on an existing receipt.json would discard a hard-linked source.
    A symlink at that name is replaced, not followed.
    """
    payload = text.encode("ascii")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    for _ in range(8):
        tmp_name = ".receipt-%d-%d.tmp" % (os.getpid(), random.SystemRandom().randrange(1 << 30))
        try:
            fd = os.open(tmp_name, flags, 0o644, dir_fd=dir_fd)
        except FileExistsError:
            continue
        try:
            view = payload
            while view:
                wrote = os.write(fd, view)
                if wrote <= 0:
                    raise OSError("short receipt write")
                view = view[wrote:]
            os.fsync(fd)
        except Exception:
            os.close(fd)
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
            raise
        os.close(fd)
        try:
            os.replace(tmp_name, "receipt.json", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        except OSError:
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
            raise
        return
    raise OSError("receipt replace failed")


def child_env(scratch):
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": CHILD_PATH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": scratch,
    }


def close_stream(stream):
    if stream is None or stream.closed:
        return
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return


def drain(stream, limit, truncated_event, sink):
    total = 0
    chunks = []
    truncated = False
    try:
        while True:
            block = stream.read(65536)
            if not block:
                break
            room = limit - total
            if room <= 0:
                truncated = True
                truncated_event.set()
                break
            if len(block) > room:
                chunks.append(block[:room])
                total += room
                truncated = True
                truncated_event.set()
                break
            chunks.append(block)
            total += len(block)
    finally:
        sink["data"] = b"".join(chunks)
        sink["truncated"] = truncated
        sink["bytes"] = total


def run_one(spec, scratch, stdin_bytes, timeout, max_output):
    row = step_shell(spec)
    row["started_at"] = utc_now()
    if stdin_bytes:
        row["stdin_bytes"] = len(stdin_bytes)
        row["stdin_sha256"] = sha256_bytes(stdin_bytes)
    try:
        proc = subprocess.Popen(
            list(spec.argv),
            cwd=scratch,
            env=child_env(scratch),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
    except FileNotFoundError:
        row["technical_status"] = "start-failed"
        row["exit_code"] = 127
        row["finished_at"] = utc_now()
        return row
    out_sink = {"data": b"", "truncated": False, "bytes": 0}
    err_sink = {"data": b"", "truncated": False, "bytes": 0}
    truncated = threading.Event()
    out_thread = threading.Thread(
        target=drain, args=(proc.stdout, max_output, truncated, out_sink), daemon=True
    )
    err_thread = threading.Thread(
        target=drain, args=(proc.stderr, max_output, truncated, err_sink), daemon=True
    )
    out_thread.start()
    err_thread.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    pending = memoryview(stdin_bytes) if stdin_bytes else None
    sent = 0
    stdin_open = proc.stdin is not None
    if stdin_open:
        os.set_blocking(proc.stdin.fileno(), False)
    try:
        while True:
            if truncated.is_set():
                kill_group(proc)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                kill_group(proc)
                break
            if stdin_open and pending is not None:
                try:
                    wrote = os.write(proc.stdin.fileno(), pending[sent:])
                except BlockingIOError:
                    wrote = 0
                except (BrokenPipeError, OSError):
                    pending = None
                    close_stream(proc.stdin)
                    stdin_open = False
                    wrote = 0
                else:
                    if wrote > 0:
                        sent += wrote
                    if sent >= len(pending):
                        pending = None
                        close_stream(proc.stdin)
                        stdin_open = False
            elif stdin_open:
                close_stream(proc.stdin)
                stdin_open = False
            if proc.poll() is not None and not stdin_open:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                kill_group(proc)
                break
            slice_wait = min(0.05, remaining)
            if stdin_open:
                try:
                    select.select([], [proc.stdin.fileno()], [], slice_wait)
                except (ValueError, OSError):
                    close_stream(proc.stdin)
                    stdin_open = False
            else:
                try:
                    proc.wait(timeout=slice_wait)
                    break
                except subprocess.TimeoutExpired:
                    continue
        out_thread.join(timeout=5)
        err_thread.join(timeout=5)
        if out_thread.is_alive() or err_thread.is_alive():
            timed_out = True
            kill_group(proc)
        stdout = out_sink.get("data", b"")
        stderr = err_sink.get("data", b"")
        row["stdout_bytes"] = out_sink.get("bytes", len(stdout))
        row["stderr_bytes"] = err_sink.get("bytes", len(stderr))
        row["stdout_sha256"] = sha256_bytes(stdout)
        row["stderr_sha256"] = sha256_bytes(stderr)
        row["stdout_truncated"] = bool(out_sink.get("truncated"))
        row["stderr_truncated"] = bool(err_sink.get("truncated"))
        row["exit_code"] = proc.returncode
        if timed_out:
            row["technical_status"] = "timeout"
        elif row["stdout_truncated"] or row["stderr_truncated"]:
            row["technical_status"] = "output-limit"
        else:
            row["technical_status"] = "executed"
            if row["exit_code"] == spec.map_expected_exit:
                row["actual_vs_map"] = "match"
            else:
                row["actual_vs_map"] = "mismatch"
        row["finished_at"] = utc_now()
        return row
    finally:
        if proc.poll() is None:
            kill_group(proc)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            close_stream(stream)


def count_bytecode(root):
    found = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath) == "__pycache__":
            found += 1
        found += sum(1 for name in filenames if name.endswith(".pyc"))
    return found


def write_bodies(scratch, bodies):
    dir_fd = os.open(scratch, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name, blob in bodies.items():
            if not SAFE_NAME.fullmatch(name) or "/" in name:
                raise Problem("scratch-failed")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
            fd = os.open(name, flags, 0o644, dir_fd=dir_fd)
            try:
                view = blob
                while view:
                    wrote = os.write(fd, view)
                    view = view[wrote:]
                os.fsync(fd)
            finally:
                os.close(fd)
        for name, blob in bodies.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
            try:
                got = os.read(fd, len(blob) + 1)
            finally:
                os.close(fd)
            if got != blob:
                raise Problem("scratch-failed")
    finally:
        os.close(dir_fd)


def relate_stdout(steps):
    by_id = {row["id"]: row for row in steps}
    for spec in STEP_TABLE:
        if not spec.stdout_same_as:
            continue
        row = by_id[spec.id]
        other = by_id[spec.stdout_same_as]
        if (
            row["technical_status"] == "executed"
            and other["technical_status"] == "executed"
            and not row["stdout_truncated"]
            and not other["stdout_truncated"]
            and row["stdout_sha256"]
            and other["stdout_sha256"]
        ):
            row["stdout_relation"] = "match" if row["stdout_sha256"] == other["stdout_sha256"] else "mismatch"
        else:
            row["stdout_relation"] = "not-compared"


def execute_steps(scratch, bodies, fixtures, timeout, max_output):
    rows = []
    stopped = False
    for spec in STEP_TABLE:
        if stopped:
            rows.append(step_shell(spec))
            continue
        if spec.stdin_kind == "status_input":
            stdin_bytes = bodies["status_input.json"]
        elif spec.stdin_kind is None:
            stdin_bytes = b""
        else:
            stdin_bytes = fixtures[spec.stdin_kind]
        row = run_one(spec, scratch, stdin_bytes, timeout, max_output)
        rows.append(row)
        if row["technical_status"] != "executed":
            stopped = True
    relate_stdout(rows)
    return rows


def finish(receipt, code, dir_fd):
    text = dumps(receipt)
    if dir_fd is not None:
        try:
            write_receipt(dir_fd, text)
        except OSError:
            receipt["reason"] = receipt["reason"] or "output-dir-unsafe"
            code = 2 if code == 0 else code
            text = dumps(receipt)
    return code, receipt, text


def apply_archive(receipt, data_public, identity):
    receipt["archive"]["bytes"] = data_public["bytes"]
    receipt["archive"]["sha256"] = data_public["sha256"]
    receipt["archive"]["safety"] = data_public["safety"]
    receipt["archive"]["safety_reasons"] = list(data_public["safety_reasons"])
    receipt["archive"]["layout"] = data_public["layout"]
    receipt["archive"]["regular_files"] = data_public["regular_files"]
    receipt["archive"]["uncompressed_bytes"] = data_public["uncompressed_bytes"]
    receipt["members"] = list(data_public["members"])
    receipt["archive"]["identity"] = compare_identity(data_public, identity)
    receipt["required_identity"] = identity_public(identity)


def refuse(receipt, reason, technical="refused"):
    receipt["reason"] = reason
    receipt["technical_status"] = technical
    receipt["executed"] = False
    receipt["s1_judgment"] = "NOT_TESTED"


def perform(
    zip_path,
    output_dir,
    *,
    execute,
    dedicated_vm,
    binding_path,
    fixture_dir,
    identity,
    timeout,
    max_output,
):
    mode = "execute" if execute else "inspect"
    receipt = base_receipt(mode)
    receipt["required_identity"] = identity_public(identity)
    dir_fd = None
    try:
        receipt["tool_file_sha256"] = tool_file_sha256()
        if execute and not dedicated_vm:
            raise Problem("dedicated-vm-acknowledgement-required")
        if execute and not binding_path:
            raise Problem("binding-required")
        if execute and not fixture_dir:
            raise Problem("fixture-dir-required")
        dir_fd = output_dir_fd(zip_path, output_dir)
        data, mode_bits = read_zip(zip_path)
        measured = measure(data)
        apply_archive(receipt, measured.public, identity)
        if not confirm_source(zip_path, data, mode_bits):
            receipt["archive"]["source_unchanged"] = False
            raise Problem("source-changed")
        receipt["archive"]["source_unchanged"] = True
        if measured.public["safety"] != "clear":
            raise Problem("zip-unsafe")
        if receipt["archive"]["identity"] == "mismatch":
            raise Problem("identity-mismatch")
        if receipt["archive"]["identity"] == "census-conflict":
            raise Problem("census-conflict")
        if measured.public["layout"] != "flat":
            if execute:
                raise Problem("layout-not-flat")
        binding = None
        if binding_path:
            binding = load_binding(binding_path)
            status, problems = assess_binding(measured, binding)
            receipt["binding_status"] = status
            receipt["binding_problems"] = problems
            if execute and status == "sha-mismatch":
                raise Problem("member-sha-mismatch")
            if execute and status != "complete":
                raise Problem("binding-incomplete")
        elif execute:
            raise Problem("binding-required")
        if not execute:
            receipt["technical_status"] = "inspect-only"
            receipt["executed"] = False
            receipt["s1_judgment"] = "NOT_TESTED"
            code = 2 if receipt["binding_status"] == "invalid" else 0
            return finish(receipt, code, dir_fd)
        fixtures = {}
        for step_id, rule_bytes in STDIN_SIZES.items():
            item = binding["stdin_fixtures"][step_id]
            blob = read_fixture(fixture_dir, item["name"], rule_bytes)
            if sha256_bytes(blob) != item["sha256"]:
                raise Problem("fixture-sha-mismatch")
            fixtures[step_id] = blob
        checked_fd = output_dir_fd(zip_path, output_dir)
        try:
            if not os.path.samestat(os.fstat(checked_fd), os.fstat(dir_fd)):
                raise Problem("output-dir-unsafe")
            scratch = tempfile.mkdtemp(prefix="s1scratch-", dir=os.path.abspath(output_dir))
        finally:
            os.close(checked_fd)
        receipt["scratch"] = "created"
        try:
            write_bodies(scratch, measured.bodies)
            for name in ENTRY_MEMBERS:
                if name not in measured.bodies:
                    raise Problem("scratch-failed")
            rows = execute_steps(scratch, measured.bodies, fixtures, timeout, max_output)
            receipt["steps"] = rows
            receipt["executed"] = True
            receipt["pycache_entries"] = count_bytecode(scratch)
            statuses = [row["technical_status"] for row in rows]
            if any(item != "executed" for item in statuses):
                receipt["technical_status"] = "interrupted"
                if "timeout" in statuses:
                    receipt["reason"] = "timeout"
                elif "output-limit" in statuses:
                    receipt["reason"] = "output-limit"
                else:
                    receipt["reason"] = "start-failed"
            else:
                receipt["technical_status"] = "complete"
                receipt["reason"] = None
        finally:
            try:
                shutil.rmtree(scratch)
                receipt["scratch"] = "removed"
            except OSError:
                receipt["scratch"] = "remove-failed"
                receipt["reason"] = "scratch-remove-failed"
        if not confirm_source(zip_path, data, mode_bits):
            receipt["archive"]["source_unchanged"] = False
            receipt["reason"] = "source-changed"
        receipt["s1_judgment"] = "NOT_TESTED"
        receipt["preflight_normalized_to_pass"] = False
        if receipt["reason"] in ("timeout", "output-limit", "start-failed", "source-changed", "scratch-remove-failed"):
            return finish(receipt, 1, dir_fd)
        return finish(receipt, 0, dir_fd)
    except OSError:
        refuse(receipt, "scratch-failed")
        return finish(receipt, 1, dir_fd)
    except Problem as error:
        refuse(receipt, error.reason)
        code = 1 if error.reason in {
            "unreadable-zip",
            "zip-is-symlink",
            "not-regular-file",
            "zip-too-large",
            "source-changed",
            "zip-unsafe",
            "identity-mismatch",
            "census-conflict",
            "member-sha-mismatch",
            "fixture-sha-mismatch",
            "fixture-length",
            "fixture-unreadable",
            "timeout",
            "output-limit",
            "start-failed",
            "scratch-failed",
        } else 2
        return finish(receipt, code, dir_fd)
    finally:
        if dir_fd is not None:
            os.close(dir_fd)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect a frozen ZIP. Execute only the fixed eight Python steps after binding checks."
    )
    parser.add_argument("--zip", required=True, dest="zip_path")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--binding")
    parser.add_argument("--fixture-dir")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dedicated-vm", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    code, receipt, text = perform(
        args.zip_path,
        args.output_dir,
        execute=args.execute,
        dedicated_vm=args.dedicated_vm,
        binding_path=args.binding,
        fixture_dir=args.fixture_dir,
        identity=FROZEN,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_output=MAX_STREAM_BYTES,
    )
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
