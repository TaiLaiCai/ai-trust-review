#!/usr/bin/env python3
"""Read-only byte validation; no receipt authentication or trust decision."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

MAX_MANIFEST = 1024 * 1024
MAX_FILES = 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


class InvalidManifest(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidManifest("duplicate JSON key")
        result[key] = value
    return result


def relative_parts(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise InvalidManifest("invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise InvalidManifest("path must be canonical and stay within package")
    if ":" in value or value == "manifest.json":
        raise InvalidManifest("unsupported path or manifest self-reference")
    return path.parts


def open_regular(root_fd, parts):
    """Walk descriptors without following links, including final-file links."""
    parent = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise OSError("artifact is not a regular file")
        return os.fdopen(fd, "rb")
    finally:
        os.close(parent)


def read_manifest(root_fd):
    with open_regular(root_fd, ("manifest.json",)) as stream:
        raw = stream.read(MAX_MANIFEST + 1)
    if len(raw) > MAX_MANIFEST:
        raise InvalidManifest("manifest exceeds size limit")
    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(obj, dict) or set(obj) != {"schema_version", "artifacts"}:
        raise InvalidManifest("expected schema_version and artifacts only")
    if obj["schema_version"] != "evidence-package/v1":
        raise InvalidManifest("unknown schema version")
    artifacts = obj["artifacts"]
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= MAX_FILES:
        raise InvalidManifest("expected 1..1024 artifacts")
    seen = set()
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise InvalidManifest("each artifact needs path and sha256 only")
        relative_parts(item["path"])
        if item["path"] in seen:
            raise InvalidManifest("duplicate artifact path")
        seen.add(item["path"])
        if not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise InvalidManifest("sha256 must be 64 lowercase hex characters")
    return artifacts


def verify(root):
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        artifacts = read_manifest(root_fd)
        checked, total = [], 0
        for item in artifacts:
            digest, size = hashlib.sha256(), 0
            with open_regular(root_fd, relative_parts(item["path"])) as stream:
                while chunk := stream.read(64 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                        raise OSError("artifact byte budget exceeded")
                    digest.update(chunk)
            actual = digest.hexdigest()
            if actual != item["sha256"]:
                return {"verdict": "FAIL", "reason": "sha256 mismatch", "path": item["path"]}
            checked.append({"path": item["path"], "bytes": size, "sha256": actual})
        return {"verdict": "PASS", "scope": "artifact-bytes-only", "artifacts": checked}
    finally:
        os.close(root_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="trusted operator-selected package root")
    args = parser.parse_args()
    try:
        result = verify(args.root)
        code = 0 if result["verdict"] == "PASS" else 1
    except (ValueError, RecursionError) as error:
        result, code = {"verdict": "FAIL", "reason": str(error)}, 2
    except OSError:
        result, code = {"verdict": "FAIL", "reason": "missing, unsafe or unreadable package file"}, 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
