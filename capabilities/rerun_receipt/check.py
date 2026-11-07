#!/usr/bin/env python3
"""Re-run receipts: `emit` executes manifest commands and records byte digests, `verify` is read-only; no approval, no identity authentication, no stage writes."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess

VERSION = "v1"
SCHEMA_MANIFEST = "rerun-manifest/v1"
SCHEMA_RECEIPTS = "rerun-receipt/v1"

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_RECEIPTS_BYTES = 4 * 1024 * 1024
MAX_COMMANDS = 1024
MAX_ARGC = 64
MAX_ARG_BYTES = 4096
MAX_ID_BYTES = 64
MAX_STR_BYTES = 128
MAX_EVIDENCE_FILE_BYTES = 64 * 1024 * 1024
MAX_EVIDENCE_TOTAL_BYTES = 256 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 600

HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
ID_RE = re.compile(r"[0-9a-z][0-9a-z-]{0,63}")
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class InvalidContract(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidContract("duplicate JSON key")
        result[key] = value
    return result


def load_json(path, max_bytes, what):
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise InvalidContract(f"{what} exceeds size limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except UnicodeDecodeError as error:
        raise InvalidContract(f"{what} is not UTF-8") from error
    except json.JSONDecodeError as error:
        raise InvalidContract(f"{what} is not valid JSON") from error


def check_str(value, max_bytes, label):
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > max_bytes:
        raise InvalidContract(f"{label} must be a non-empty string within {max_bytes} bytes")
    return value


def check_argv(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ARGC:
        raise InvalidContract("argv must be a list of 1..%d items" % MAX_ARGC)
    for item in value:
        if not isinstance(item, str) or not item or len(item.encode("utf-8")) > MAX_ARG_BYTES:
            raise InvalidContract("argv items must be non-empty strings within %d bytes" % MAX_ARG_BYTES)
    return value


def validate_manifest(obj):
    if not isinstance(obj, dict) or set(obj) != {"schema_version", "head_sha", "commands"}:
        raise InvalidContract("manifest needs schema_version, head_sha and commands only")
    if obj["schema_version"] != SCHEMA_MANIFEST:
        raise InvalidContract("unknown manifest schema version")
    if not isinstance(obj["head_sha"], str) or not HEX40.fullmatch(obj["head_sha"]):
        raise InvalidContract("head_sha must be 40 lowercase hex characters")
    commands = obj["commands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_COMMANDS:
        raise InvalidContract("expected 1..%d commands" % MAX_COMMANDS)
    seen = set()
    normalized = []
    for item in commands:
        if not isinstance(item, dict):
            raise InvalidContract("each command is an object")
        if set(item) not in ({"id", "argv"}, {"id", "argv", "expect_exit"}):
            raise InvalidContract("command keys must be id, argv and optional expect_exit")
        identifier = check_str(item["id"], MAX_ID_BYTES, "id")
        if not ID_RE.fullmatch(identifier) or identifier in seen:
            raise InvalidContract("id must match [0-9a-z][0-9a-z-]{0,63} and be unique")
        seen.add(identifier)
        argv = check_argv(item["argv"])
        expect = item.get("expect_exit")
        if expect is not None and (type(expect) is not int or not 0 <= expect <= 255):
            raise InvalidContract("expect_exit must be an integer 0..255 when present")
        normalized.append((identifier, argv, expect))
    return obj["head_sha"], normalized


def validate_receipts(obj):
    if not isinstance(obj, dict) or set(obj) != {"schema_version", "head_sha", "generated_at",
                                                "runner", "receipts"}:
        raise InvalidContract("receipts need schema_version, head_sha, generated_at, runner and receipts only")
    if obj["schema_version"] != SCHEMA_RECEIPTS:
        raise InvalidContract("unknown receipts schema version")
    if not isinstance(obj["head_sha"], str) or not HEX40.fullmatch(obj["head_sha"]):
        raise InvalidContract("head_sha must be 40 lowercase hex characters")
    if not isinstance(obj["generated_at"], str) or not TS_RE.fullmatch(obj["generated_at"]):
        raise InvalidContract("generated_at must be an RFC3339 UTC second-resolution timestamp")
    runner = obj["runner"]
    if not isinstance(runner, dict) or set(runner) != {"account", "agent", "model", "os", "python"}:
        raise InvalidContract("runner needs account, agent, model, os and python only")
    for key in ("account", "agent", "model", "os", "python"):
        check_str(runner[key], MAX_STR_BYTES, f"runner.{key}")
    receipts = obj["receipts"]
    if not isinstance(receipts, list) or not 1 <= len(receipts) <= MAX_COMMANDS:
        raise InvalidContract("expected 1..%d receipts" % MAX_COMMANDS)
    seen = set()
    for item in receipts:
        if not isinstance(item, dict) or set(item) != {"id", "argv", "exit_code", "stdout_sha256",
                                                        "stderr_sha256", "started_at", "finished_at"}:
            raise InvalidContract("receipt keys must be id, argv, exit_code, stdout_sha256, stderr_sha256, started_at, finished_at")
        identifier = check_str(item["id"], MAX_ID_BYTES, "id")
        if not ID_RE.fullmatch(identifier) or identifier in seen:
            raise InvalidContract("receipt id must match [0-9a-z][0-9a-z-]{0,63} and be unique")
        seen.add(identifier)
        check_argv(item["argv"])
        code = item["exit_code"]
        if type(code) is not int or not -128 <= code <= 255:
            raise InvalidContract("exit_code must be an integer -128..255")
        for key in ("stdout_sha256", "stderr_sha256"):
            if not isinstance(item[key], str) or not HEX64.fullmatch(item[key]):
                raise InvalidContract(f"{key} must be 64 lowercase hex characters")
        for key in ("started_at", "finished_at"):
            if not isinstance(item[key], str) or not TS_RE.fullmatch(item[key]):
                raise InvalidContract(f"{key} must be an RFC3339 UTC second-resolution timestamp")
    return obj


def git_head(repo):
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    head = proc.stdout.strip()
    return head if HEX40.fullmatch(head) else None


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(manifest_path, repo, out_path, evidence_dir, runner_labels, timeout):
    manifest = validate_manifest(load_json(manifest_path, MAX_MANIFEST_BYTES, "manifest"))
    head_manifest, commands = manifest
    for key, value in runner_labels.items():
        check_str(value, MAX_STR_BYTES, f"runner.{key}")
    if evidence_dir.is_symlink() or (evidence_dir.exists() and not evidence_dir.is_dir()):
        raise InvalidContract("evidence directory must be a real directory")
    head_actual = git_head(repo)
    if head_actual is None:
        return {"verdict": "FAIL", "reason": "cannot read repository HEAD"}, 2
    if head_actual != head_manifest:
        return {"verdict": "FAIL", "reason": "manifest head_sha differs from repository HEAD",
                "manifest": head_manifest, "actual": head_actual}, 2
    evidence_dir.mkdir(parents=True, exist_ok=True)
    receipts, results = [], []
    for identifier, argv, expect in commands:
        started = now_utc()
        try:
            proc = subprocess.run(argv, cwd=str(repo), capture_output=True, timeout=timeout)
            code, out_bytes, err_bytes = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            code, out_bytes, err_bytes = -9, b"", f"<timeout after {timeout}s>\n".encode()
        except FileNotFoundError as error:
            code, out_bytes, err_bytes = 127, b"", f"<spawn failed: {error}>\n".encode()
        except OSError as error:
            code, out_bytes, err_bytes = 126, b"", f"<spawn failed: {error}>\n".encode()
        finished = now_utc()
        (evidence_dir / f"{identifier}.stdout").write_bytes(out_bytes)
        (evidence_dir / f"{identifier}.stderr").write_bytes(err_bytes)
        receipts.append({
            "id": identifier, "argv": argv, "exit_code": code,
            "stdout_sha256": hashlib.sha256(out_bytes).hexdigest(),
            "stderr_sha256": hashlib.sha256(err_bytes).hexdigest(),
            "started_at": started, "finished_at": finished,
        })
        results.append({"id": identifier, "exit_code": code, "expect_exit": expect,
                        "ok": expect is None or expect == code})
    document = {
        "schema_version": SCHEMA_RECEIPTS, "head_sha": head_actual, "generated_at": now_utc(),
        "runner": runner_labels, "receipts": receipts,
    }
    out_path.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    verdict = {"verdict": "PASS" if all(row["ok"] for row in results) else "FAIL",
               "receipts_path": str(out_path), "head_sha": head_actual, "results": results}
    return verdict, 0 if verdict["verdict"] == "PASS" else 1


def open_regular(path):
    parent = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError("not a regular file")
    return os.fdopen(fd, "rb")


def digest_stream(stream, remaining_budget):
    digest, size = hashlib.sha256(), 0
    while chunk := stream.read(64 * 1024):
        size += len(chunk)
        remaining_budget -= len(chunk)
        if size > MAX_EVIDENCE_FILE_BYTES or remaining_budget < 0:
            raise OSError("evidence byte budget exceeded")
        digest.update(chunk)
    return digest.hexdigest(), size


def verify(manifest_path, receipts_path, evidence_dir):
    head_manifest, commands = validate_manifest(
        load_json(manifest_path, MAX_MANIFEST_BYTES, "manifest"))
    document = validate_receipts(
        load_json(receipts_path, MAX_RECEIPTS_BYTES, "receipts"))
    if document["head_sha"] != head_manifest:
        return {"verdict": "FAIL", "reason": "receipts head_sha differs from manifest",
                "scope": "contract"}, 2
    by_id = {item["id"]: item for item in document["receipts"]}
    for identifier, argv, expect in commands:
        item = by_id.get(identifier)
        if item is None:
            return {"verdict": "FAIL", "reason": f"missing receipt for {identifier}"}, 1
        if item["argv"] != argv:
            return {"verdict": "FAIL", "reason": f"argv differs for {identifier}"}, 1
        if expect is not None and item["exit_code"] != expect:
            return {"verdict": "FAIL", "reason": f"exit_code differs from expect_exit for {identifier}",
                    "id": identifier, "exit_code": item["exit_code"], "expect_exit": expect}, 1
    extras = sorted(set(by_id) - {identifier for identifier, _, _ in commands})
    if extras:
        return {"verdict": "FAIL", "reason": "receipts contain commands absent from manifest",
                "extra_ids": extras}, 1
    if evidence_dir is not None:
        if evidence_dir.is_symlink() or not evidence_dir.is_dir():
            return {"verdict": "FAIL", "reason": "missing or unsafe evidence directory"}, 1
        budget = MAX_EVIDENCE_TOTAL_BYTES
        for identifier, _, _ in commands:
            item = by_id[identifier]
            for suffix, field in (("stdout", "stdout_sha256"), ("stderr", "stderr_sha256")):
                path = evidence_dir / f"{identifier}.{suffix}"
                try:
                    with open_regular(path) as stream:
                        actual, used = digest_stream(stream, budget)
                except OSError:
                    return {"verdict": "FAIL", "reason": f"missing or unreadable evidence {path.name}"}, 1
                budget -= used
                if actual != item[field]:
                    return {"verdict": "FAIL", "reason": f"{field} mismatch for {identifier}",
                            "id": identifier, "field": field}, 1
        scope = "receipts-plus-evidence-bytes"
    else:
        scope = "receipts-schema-only"
    return {"verdict": "PASS", "scope": scope, "head_sha": head_manifest,
            "checked": [{"id": identifier, "exit_code": by_id[identifier]["exit_code"]}
                        for identifier, _, _ in commands]}, 0


def self_fingerprint():
    digest = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
    return f"{VERSION} {digest}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="store_true",
                        help="print version and full sha256 of this file, then exit 0")
    sub = parser.add_subparsers(dest="command")

    p_emit = sub.add_parser("emit", help="execute manifest commands and write receipts")
    p_emit.add_argument("manifest", type=Path)
    p_emit.add_argument("--repo", type=Path, required=True, help="repository root used as cwd and HEAD source")
    p_emit.add_argument("--out", type=Path, help="receipts output path (default: <manifest dir>/receipts.json)")
    p_emit.add_argument("--evidence", type=Path, help="evidence directory (default: <manifest dir>/evidence)")
    p_emit.add_argument("--runner-account", default="unspecified")
    p_emit.add_argument("--runner-agent", default="unspecified")
    p_emit.add_argument("--runner-model", default="unspecified")
    p_emit.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    p_verify = sub.add_parser("verify", help="read-only check of receipts against the manifest")
    p_verify.add_argument("manifest", type=Path)
    p_verify.add_argument("receipts", type=Path)
    p_verify.add_argument("--evidence", type=Path, help="optional directory with <id>.stdout/.stderr bytes")

    args = parser.parse_args()
    if args.version or args.command is None:
        if args.version:
            print(self_fingerprint())
            return 0
        parser.print_help()
        return 2

    try:
        if args.command == "emit":
            out = args.out or args.manifest.parent / "receipts.json"
            evidence = args.evidence or args.manifest.parent / "evidence"
            runner_labels = {
                "account": args.runner_account, "agent": args.runner_agent,
                "model": args.runner_model,
                "os": f"{platform.system()} {platform.release()} {platform.machine()}",
                "python": platform.python_version(),
            }
            result, code = emit(args.manifest, args.repo, out, evidence, runner_labels, args.timeout)
        else:
            result, code = verify(args.manifest, args.receipts, args.evidence)
    except InvalidContract as error:
        result, code = {"verdict": "FAIL", "reason": str(error), "scope": "contract"}, 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
