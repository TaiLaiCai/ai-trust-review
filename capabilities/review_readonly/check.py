#!/usr/bin/env python3
"""C-R5-2: compare a trusted before-review manifest to current file bytes.

`--file` records an explicit set. `--tree` records every regular file under a
directory so a file added later is part of the comparison. The process exit
code is the delivery gate (0 only when delivery_allowed is true).
"""
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


def normalize_tree(tree):
    if tree == ".":
        return "."
    path_parts(tree)
    return tree


def under_tree(path, tree):
    if tree == ".":
        return True
    return path.startswith(tree + "/")


@contextmanager
def open_root(root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        yield fd
    finally:
        os.close(fd)


def directory_fd_path(fd):
    proc = f"/proc/self/fd/{fd}"
    if os.path.exists(proc):
        return proc
    dev = f"/dev/fd/{fd}"
    if os.path.exists(dev):
        return dev
    raise InputError("directory listing needs /proc/self/fd or /dev/fd")


def digest_fd(fd, forbidden_id=None):
    before = os.fstat(fd)
    if forbidden_id and (before.st_dev, before.st_ino) == forbidden_id:
        raise InputError("baseline inode is inside the reviewed set")
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


def read_target(root_fd, path, forbidden_id=None):
    fd = os.dup(root_fd)
    try:
        parts = path_parts(path)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            return digest_fd(child, forbidden_id)
        finally:
            os.close(child)
    finally:
        os.close(fd)


def list_directory(fd):
    before = os.fstat(fd)
    if not stat.S_ISDIR(before.st_mode):
        raise InputError("tree is not a directory")
    names = os.listdir(directory_fd_path(fd))
    after = os.fstat(fd)
    if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
        raise InputError("directory changed while reading")
    return names


def entry_kind(dir_fd, name):
    mode = os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode
    if stat.S_ISLNK(mode):
        raise InputError("symlink in tree")
    if stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
        raise InputError("special file in tree")
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISREG(mode):
        return "file"
    raise InputError("unsupported file in tree")


def open_tree(root_fd, tree):
    fd = os.dup(root_fd)
    try:
        if tree != ".":
            for part in path_parts(tree):
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def walk_tree(root_fd, tree, forbidden_id=None):
    found = {}
    prefix = "" if tree == "." else tree
    stack = [(open_tree(root_fd, tree), prefix)]
    try:
        while stack:
            fd, rel_dir = stack.pop()
            try:
                for name in sorted(list_directory(fd)):
                    rel = name if not rel_dir else f"{rel_dir}/{name}"
                    try:
                        path_parts(rel)
                        kind = entry_kind(fd, name)
                        if kind == "dir":
                            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                            stack.append((child, rel))
                            continue
                        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    except FileNotFoundError:
                        continue
                    try:
                        found[rel] = digest_fd(file_fd, forbidden_id)
                    finally:
                        os.close(file_fd)
            finally:
                os.close(fd)
        return found
    except Exception:
        while stack:
            os.close(stack.pop()[0])
        raise


def remember(files, total, path, meta):
    if path in files:
        if files[path] != meta:
            raise InputError("file and tree metadata disagree")
        return total
    total += meta["bytes"]
    if total > MAX_TOTAL:
        raise InputError("total bytes exceed limit")
    if len(files) + 1 > MAX_FILES:
        raise InputError("file count exceeds limit")
    files[path] = meta
    return total


def snapshot(root, paths=None, trees=None):
    if paths is None:
        paths = []
    if trees is None:
        trees = []
    if not isinstance(paths, list) or not isinstance(trees, list):
        raise InputError("expected explicit files or trees")
    if not paths and not trees:
        raise InputError("expected explicit files or trees")
    if len(paths) > MAX_FILES or len(trees) > MAX_FILES:
        raise InputError("file count exceeds limit")
    for path in paths:
        path_parts(path)
    if len(set(paths)) != len(paths):
        raise InputError("duplicate target path")
    norm_trees = [normalize_tree(tree) for tree in trees]
    if len(set(norm_trees)) != len(norm_trees):
        raise InputError("duplicate tree path")
    root = os.path.abspath(root)
    files, total = {}, 0
    with open_root(root) as fd:
        for path in sorted(paths):
            total = remember(files, total, path, read_target(fd, path))
        for tree in sorted(set(norm_trees)):
            for path, meta in sorted(walk_tree(fd, tree).items()):
                total = remember(files, total, path, meta)
    result = {"schema_version": SCHEMA, "root": root, "files": files}
    if norm_trees:
        result["trees"] = sorted(set(norm_trees))
    if len(canonical(result)) > MAX_MANIFEST:
        raise InputError("baseline exceeds manifest byte limit")
    return result


def parse_trees(raw_trees):
    if not isinstance(raw_trees, list) or not 1 <= len(raw_trees) <= MAX_FILES:
        raise InputError("invalid baseline trees")
    trees = []
    for tree in raw_trees:
        if not isinstance(tree, str):
            raise InputError("invalid baseline trees")
        trees.append(normalize_tree(tree))
    if trees != sorted(trees) or len(set(trees)) != len(trees):
        raise InputError("invalid baseline trees")
    return trees


def verify(root, raw, expected_sha256, forbidden_id=None):
    if not isinstance(raw, bytes) or len(raw) > MAX_MANIFEST:
        raise InputError("invalid or oversized baseline")
    if not isinstance(expected_sha256, str) or not HEX.fullmatch(expected_sha256):
        raise InputError("trusted baseline SHA256 is required")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise InputError("baseline SHA256 mismatch")
    baseline = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    root = os.path.abspath(root)
    if not isinstance(baseline, dict) or baseline.get("schema_version") != SCHEMA or baseline.get("root") != root:
        raise InputError("baseline schema or root mismatch")
    keys = set(baseline)
    if "trees" in keys:
        if keys != {"schema_version", "root", "files", "trees"}:
            raise InputError("baseline schema or root mismatch")
        trees = parse_trees(baseline["trees"])
    elif keys != {"schema_version", "root", "files"}:
        raise InputError("baseline schema or root mismatch")
    else:
        trees = []
    files = baseline["files"]
    if not isinstance(files, dict) or len(files) > MAX_FILES or (not files and not trees):
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
    added, removed, modified = [], [], []
    changed_list, actual, total = [], {}, 0
    with open_root(root) as fd:
        walked = {}
        for tree in trees:
            try:
                found = walk_tree(fd, tree, forbidden_id)
            except FileNotFoundError:
                found = {}
            for path, meta in found.items():
                if path in walked and walked[path] != meta:
                    raise InputError("overlapping trees disagree")
                walked[path] = meta
        if trees:
            for path, meta in walked.items():
                actual[path] = meta
                total += meta["bytes"]
                if total > MAX_TOTAL:
                    raise InputError("total bytes exceed limit")
                base = files.get(path)
                if base is None:
                    added.append(path)
                elif base != meta:
                    modified.append(path)
            for path in files:
                if any(under_tree(path, tree) for tree in trees) and path not in walked:
                    actual[path] = None
                    removed.append(path)
        for path in sorted(files):
            if trees and any(under_tree(path, tree) for tree in trees):
                continue
            try:
                actual[path] = read_target(fd, path, forbidden_id)
            except FileNotFoundError:
                actual[path] = None
            if actual[path] is not None:
                total += actual[path]["bytes"]
                if total > MAX_TOTAL:
                    raise InputError("total bytes exceed limit")
            if actual[path] != files[path]:
                changed_list.append(path)
                if actual[path] is None:
                    removed.append(path)
                else:
                    modified.append(path)
    if trees:
        changed = {"added": sorted(added), "removed": sorted(removed), "modified": sorted(modified)}
        any_change = any(changed.values())
        scope = "declared-tree-and-file-bytes-at-two-observations-only"
    else:
        changed = changed_list
        any_change = bool(changed_list)
        scope = "declared-file-bytes-at-two-observations-only"
    return (1 if any_change else 0), {"verdict": "CHANGED" if any_change else "UNCHANGED",
                                      "delivery_allowed": not any_change, "changed": changed,
                                      "baseline_sha256": expected_sha256, "actual": actual,
                                      "scope": scope}


def ensure_baseline_outside_root(root, baseline):
    """Reject a baseline whose resolved parent sits inside the review root.

    abspath alone misses a parent symlink that points back into the root.
    The last path component is not followed here; O_NOFOLLOW still rejects a
    symlink baseline file.
    """
    root_real = os.path.realpath(root)
    parent = os.path.realpath(os.path.dirname(os.path.abspath(baseline)) or ".")
    base_real = os.path.join(parent, os.path.basename(os.path.abspath(baseline)))
    if root_real == base_real:
        raise InputError("baseline must not be the review root")
    try:
        common = os.path.commonpath([root_real, base_real])
    except ValueError:
        return
    if common == root_real:
        raise InputError("baseline must not live inside the review root")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    pre = subs.add_parser("snapshot")
    pre.add_argument("--root", required=True)
    pre.add_argument("--file", action="append")
    pre.add_argument("--tree", action="append")
    post = subs.add_parser("verify")
    post.add_argument("--root", required=True)
    post.add_argument("--baseline", required=True)
    post.add_argument("--baseline-sha256", required=True)
    args = parser.parse_args(argv)
    if args.action == "snapshot" and not args.file and not args.tree:
        parser.error("snapshot requires at least one --file or --tree")
    try:
        if args.action == "snapshot":
            code, result = 0, snapshot(args.root, args.file or [], args.tree or [])
        else:
            ensure_baseline_outside_root(args.root, args.baseline)
            fd = os.open(args.baseline, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise InputError("baseline is not a regular file")
                forbidden_id = (info.st_dev, info.st_ino)
                with os.fdopen(os.dup(fd), "rb") as stream:
                    raw = stream.read(MAX_MANIFEST + 1)
            finally:
                os.close(fd)
            code, result = verify(args.root, raw, args.baseline_sha256, forbidden_id)
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        code, result = 5, {"verdict": "INPUT_ERROR", "delivery_allowed": False, "reason": str(error)}
    sys.stdout.buffer.write(canonical(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
