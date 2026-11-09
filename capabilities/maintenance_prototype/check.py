#!/usr/bin/env python3
"""maintenance_prototype v1 — 独立维护原型：四项阻断反例与后续事故的只读校验.

check: 读取原型文档 prototype.json，校验契约（恰好四项阻断反例、每项红绿两端
回执齐全、红端必须非零退出、绿端必须零退出、后续事故引用既有反例并另记 revision），
并做保留集边界检查（保留集仓库不得位于本仓库之内、仓库树内不得出现 retention 目录）。

本工具不认证身份、不授予权限、不写实际等级、不执行文档中记录的任何命令；
PASS 只证明本次读到的文档字节满足契约与边界。
"""
import argparse
import hashlib
import json
import os
import re
import sys

SCHEMA = "maintenance-prototype/v1"
VERSION = "v1"
ID_RE = re.compile(r"^[0-9a-z][0-9a-z-]{0,63}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DOC_BYTES = 1024 * 1024
COUNTEREXAMPLES_REQUIRED = 4
MAX_INCIDENTS = 1024
MAX_ARGV = 16
MAX_STR = 512
RETENTION_DIR_NAME = "retention"


class ContractError(Exception):
    """原型文档违反契约 → exit 2."""


class BoundaryError(Exception):
    """保留集边界被违反（保留集进入本仓库）→ exit 1."""


def no_dup_keys(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            raise ContractError("duplicate JSON key: %s" % k)
        seen.add(k)
    return dict(pairs)


def want_str(obj, key, where, max_len=MAX_STR):
    v = obj.get(key)
    if not isinstance(v, str) or not v.strip() or len(v.encode("utf-8")) > max_len:
        raise ContractError("%s.%s must be a non-empty string <= %d bytes" % (where, key, max_len))
    return v


def check_receipt(obj, where, expect_zero):
    if not isinstance(obj, dict):
        raise ContractError("%s must be an object" % where)
    if set(obj) != {"argv", "exit_code", "stdout_sha256", "stderr_sha256"}:
        raise ContractError("%s allows only argv/exit_code/stdout_sha256/stderr_sha256" % where)
    argv = obj["argv"]
    if (not isinstance(argv, list) or not 1 <= len(argv) <= MAX_ARGV
            or any(not isinstance(a, str) or not a or len(a.encode("utf-8")) > 256 for a in argv)):
        raise ContractError("%s.argv must be 1..%d non-empty strings <=256 bytes" % (where, MAX_ARGV))
    code = obj["exit_code"]
    if isinstance(code, bool) or not isinstance(code, int) or not -128 <= code <= 255:
        raise ContractError("%s.exit_code must be an int in -128..255" % where)
    if expect_zero and code != 0:
        raise ContractError("%s green receipt must record exit_code 0" % where)
    if not expect_zero and code == 0:
        raise ContractError("%s red receipt must record a nonzero exit_code" % where)
    for key in ("stdout_sha256", "stderr_sha256"):
        if not isinstance(obj[key], str) or not HEX_RE.match(obj[key]):
            raise ContractError("%s.%s must be 64 lowercase hex" % (where, key))


def load_doc(path):
    try:
        raw = open(path, "rb").read()
    except FileNotFoundError:
        raise ContractError("prototype not found: %s" % path) from None
    if len(raw) > MAX_DOC_BYTES:
        raise ContractError("prototype exceeds 1MiB")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=no_dup_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ContractError) as e:
        raise ContractError("invalid prototype JSON: %s" % e)
    if not isinstance(doc, dict):
        raise ContractError("prototype must be an object")
    return doc


def check_contract(doc):
    if set(doc) != {"schema_version", "retention", "counterexamples", "incidents"}:
        raise ContractError("top level allows only schema_version/retention/counterexamples/incidents")
    if doc["schema_version"] != SCHEMA:
        raise ContractError("schema_version must be %s" % SCHEMA)

    retention = doc["retention"]
    if not isinstance(retention, dict) or set(retention) != {"repo", "ref"}:
        raise ContractError("retention allows only repo/ref")
    repo = want_str(retention, "repo", "retention")
    want_str(retention, "ref", "retention", max_len=128)
    if not (os.path.isabs(repo) or repo.startswith(("http://", "https://", "git@"))):
        raise ContractError("retention.repo must be an absolute path or a remote URL, not a relative path")
    # 绝对路径合法与否由边界检查裁决

    cxs = doc["counterexamples"]
    if not isinstance(cxs, list) or len(cxs) != COUNTEREXAMPLES_REQUIRED:
        raise ContractError("counterexamples must contain exactly %d items" % COUNTEREXAMPLES_REQUIRED)
    ids = set()
    for i, cx in enumerate(cxs):
        where = "counterexamples[%d]" % i
        if not isinstance(cx, dict) or set(cx) != {"id", "hazard", "red", "green"}:
            raise ContractError("%s allows only id/hazard/red/green" % where)
        cid = cx["id"]
        if not isinstance(cid, str) or not ID_RE.match(cid):
            raise ContractError("%s.id must match ^[0-9a-z][0-9a-z-]{0,63}$" % where)
        if cid in ids:
            raise ContractError("duplicate counterexample id: %s" % cid)
        ids.add(cid)
        want_str(cx, "hazard", where, max_len=256)
        check_receipt(cx["red"], "%s.red" % where, expect_zero=False)
        check_receipt(cx["green"], "%s.green" % where, expect_zero=True)

    incidents = doc["incidents"]
    if not isinstance(incidents, list) or len(incidents) > MAX_INCIDENTS:
        raise ContractError("incidents must be a list of at most %d items" % MAX_INCIDENTS)
    seen = set()
    for i, inc in enumerate(incidents):
        where = "incidents[%d]" % i
        if not isinstance(inc, dict) or set(inc) != {"id", "counterexample", "revision", "green"}:
            raise ContractError("%s allows only id/counterexample/revision/green" % where)
        iid = inc["id"]
        if not isinstance(iid, str) or not ID_RE.match(iid):
            raise ContractError("%s.id must match id pattern" % where)
        if iid in seen or iid in ids:
            raise ContractError("duplicate incident id: %s" % iid)
        seen.add(iid)
        if inc["counterexample"] not in ids:
            raise ContractError("%s.counterexample must reference an existing counterexample" % where)
        want_str(inc, "revision", where, max_len=64)
        check_receipt(inc["green"], "%s.green" % where, expect_zero=True)
    return repo, len(incidents)


def repo_root():
    # capabilities/maintenance_prototype/check.py -> 仓库根
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def check_boundary(retention_repo):
    """保留集必须放独立受控仓库：不得位于本仓库之内，本仓库树内不得有 retention 目录。"""
    root = repo_root()
    if os.path.isabs(retention_repo):
        try:
            inside = os.path.commonpath([root, os.path.abspath(retention_repo)]) == root
        except ValueError:
            inside = False
        if inside:
            raise BoundaryError("retention repo must live outside this repository: %s" % retention_repo)
    # 相对路径已在契约层拒绝；http(s):// 与 git@ 形式的远端地址视为仓库外。
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        if RETENTION_DIR_NAME in dirnames:
            raise BoundaryError(
                "retention directory found inside working repo: %s"
                % os.path.join(dirpath, RETENTION_DIR_NAME))


def main(argv=None):
    ap = argparse.ArgumentParser(description="read-only check of a maintenance prototype document")
    ap.add_argument("prototype", nargs="?", help="path to prototype.json")
    ap.add_argument("--version", action="store_true", help="print version and README sha256")
    args = ap.parse_args(argv)
    if args.version:
        readme = os.path.join(os.path.dirname(__file__), "README.md")
        digest = hashlib.sha256(open(readme, "rb").read()).hexdigest()
        print(json.dumps({"version": VERSION, "readme_sha256": digest}))
        return 0
    if not args.prototype:
        ap.error("the following arguments are required: prototype")
    try:
        doc = load_doc(args.prototype)
        retention_repo, incidents = check_contract(doc)
        check_boundary(retention_repo)
    except ContractError as e:
        print(json.dumps({"verdict": "FAIL", "reason": str(e), "scope": "document-and-boundary-only"},
                         ensure_ascii=False))
        return 2
    except BoundaryError as e:
        print(json.dumps({"verdict": "FAIL", "reason": str(e), "scope": "document-and-boundary-only"},
                         ensure_ascii=False))
        return 1
    print(json.dumps({
        "verdict": "PASS",
        "scope": "document-and-boundary-only",
        "counterexamples": COUNTEREXAMPLES_REQUIRED,
        "incidents": incidents,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
