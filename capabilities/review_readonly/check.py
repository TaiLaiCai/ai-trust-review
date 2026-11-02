#!/usr/bin/env python3
"""C-R5-2: compare a trusted before-review manifest to current file bytes."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat
import sys

SCHEMA = "review-readonly/v1"
HEX = re.compile(r"[0-9a-f]{64}")
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
MAX_FILES = 1024


class InputError(ValueError):
    pass


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InputError("duplicate JSON key")
        out[key] = value
    return out


def path_parts(path):
    if (not isinstance(path, str) or not path or len(path) > 4096 or
            any(c in path for c in ("\\", ":", "\0"))):
        raise InputError("invalid relative path")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise InputError("path must be a canonical relative path")
    return parts


@contextmanager
def open_root(root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        yield fd
    finally:
        os.close(fd)


def digest_fd(fd):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise InputError("not a regular file")
    if before.st_size > MAX_FILE:
        raise InputError("file exceeds byte limit")
    sha, size = hashlib.sha256(), 0
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_FILE:
            raise InputError("file exceeds byte limit")
        sha.update(chunk)
    after = os.fstat(fd)
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns) or size != after.st_size:
        raise InputError("file changed while reading")
    return {"bytes": size, "sha256": sha.hexdigest()}


def read_target(root_fd, path):
    fd = os.dup(root_fd)
    try:
        parts = path_parts(path)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            return digest_fd(child)
        finally:
            os.close(child)
    finally:
        os.close(fd)


def snapshot(root, paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_FILES:
        raise InputError("expected 1..1024 explicit file paths")
    for path in paths:
        path_parts(path)
    if len(set(paths)) != len(paths):
        raise InputError("duplicate target path")
    root = os.path.abspath(root)
    files, total = {}, 0
    with open_root(root) as fd:
        for path in sorted(paths):
            files[path] = read_target(fd, path)
            total += files[path]["bytes"]
            if total > MAX_TOTAL:
                raise InputError("total bytes exceed limit")
    result = {"schema_version": SCHEMA, "root": root, "files": files}
    if len(canonical(result)) > MAX_MANIFEST:
        raise InputError("baseline exceeds manifest byte limit")
    return result


def verify(root, raw, expected_sha256):
    if not isinstance(raw, bytes) or len(raw) > MAX_MANIFEST:
        raise InputError("invalid or oversized baseline")
    if not isinstance(expected_sha256, str) or not HEX.fullmatch(expected_sha256):
        raise InputError("trusted baseline SHA256 is required")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise InputError("baseline SHA256 mismatch")
    baseline = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    root = os.path.abspath(root)
    if (not isinstance(baseline, dict) or set(baseline) != {"schema_version", "root", "files"} or
            baseline["schema_version"] != SCHEMA or baseline["root"] != root):
        raise InputError("baseline schema or root mismatch")
    files = baseline["files"]
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise InputError("empty or invalid baseline file set")
    total = 0
    for path, item in files.items():
        path_parts(path)
        if (not isinstance(item, dict) or set(item) != {"bytes", "sha256"} or
                type(item["bytes"]) is not int or not 0 <= item["bytes"] <= MAX_FILE or
                not isinstance(item["sha256"], str) or not HEX.fullmatch(item["sha256"])):
            raise InputError("invalid baseline file metadata")
        total += item["bytes"]
    if total > MAX_TOTAL:
        raise InputError("baseline total bytes exceed limit")
    changed, actual, total = [], {}, 0
    with open_root(root) as fd:
        for path in sorted(files):
            try:
                actual[path] = read_target(fd, path)
            except FileNotFoundError:
                actual[path] = None
            if actual[path] is not None:
                total += actual[path]["bytes"]
                if total > MAX_TOTAL:
                    raise InputError("total bytes exceed limit")
            if actual[path] != files[path]:
                changed.append(path)
    return (1 if changed else 0), {"verdict": "CHANGED" if changed else "UNCHANGED",
                                  "delivery_allowed": not changed, "changed": changed,
                                  "baseline_sha256": expected_sha256, "actual": actual,
                                  "scope": "declared-file-bytes-at-two-observations-only"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    pre = subs.add_parser("snapshot")
    pre.add_argument("--root", required=True)
    pre.add_argument("--file", action="append", required=True)
    post = subs.add_parser("verify")
    post.add_argument("--root", required=True)
    post.add_argument("--baseline", required=True)
    post.add_argument("--baseline-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "snapshot":
            code, result = 0, snapshot(args.root, args.file)
        else:
            fd = os.open(args.baseline, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise InputError("baseline is not a regular file")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(MAX_MANIFEST + 1)
            finally:
                os.close(fd)
            code, result = verify(args.root, raw, args.baseline_sha256)
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        code, result = 5, {"verdict": "INPUT_ERROR", "delivery_allowed": False, "reason": str(error)}
    sys.stdout.buffer.write(canonical(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
