#!/usr/bin/env python3
"""Bot payload: the untrusted side of the isolation probe.

This file is what an untrusted Bot would run. It is executed as a real child
process under the sandbox/permission boundary, so its attempt to write is
refused by the kernel (or by the filesystem), never by this script deciding
that a path "looks wrong".

It never inspects a policy, never decides whether an attempt is allowed, and
never writes anything the boundary did not let it write. All of that is the
boundary's job. The only thing this file does is attempt the write and report
what actually happened, as JSON on stdout.

Exit codes:
  0  the write happened (the boundary allowed it)
  3  the write was refused by the kernel or the filesystem
  5  the payload could not run at all (bad arguments, missing target)
"""
import argparse
import errno
import json
import os

# A write that is expected to succeed inside the sandbox.
ALLOWED = "allowed"
# A write that the boundary is expected to refuse.
DENIED = "denied"


def errno_name(code):
    """Name for an errno value, or EUNKNOWN when the platform does not have it."""
    return errno.errorcode.get(code, "EUNKNOWN") if code is not None else "EUNKNOWN"


def attempt_write(path, mode="wb"):
    """Try to write to `path` and report the real outcome.

    Returns a dict with the observed result. It does not decide whether the
    result was correct; the caller compares it against what the boundary
    promised.
    """
    result = {
        "path": path,
        "attempted": True,
        "refused": False,
        "errno": None,
        "errno_name": None,
        "detail": None,
        "bytes_written": 0,
    }
    try:
        if mode == "append":
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        else:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            payload = b"PROBE-WRITE\n"
            written = os.write(fd, payload)
            result["bytes_written"] = written
        finally:
            os.close(fd)
    except OSError as error:
        result["refused"] = True
        result["errno"] = error.errno
        result["errno_name"] = errno_name(error.errno)
        result["detail"] = error.strerror
    return result


def attempt_read(path):
    """Try to read `path` and report the real outcome."""
    result = {
        "path": path,
        "attempted": True,
        "refused": False,
        "errno": None,
        "errno_name": None,
        "detail": None,
        "bytes_read": 0,
    }
    try:
        with open(path, "rb") as handle:
            data = handle.read(65536)
        result["bytes_read"] = len(data)
    except OSError as error:
        result["refused"] = True
        result["errno"] = error.errno
        result["errno_name"] = errno_name(error.errno)
        result["detail"] = error.strerror
    return result


def attempt_chmod(path, mode):
    """Try to change the mode of `path` (an escape attempt)."""
    result = {
        "path": path,
        "attempted": True,
        "refused": False,
        "errno": None,
        "errno_name": None,
        "detail": None,
    }
    try:
        os.chmod(path, mode)
    except OSError as error:
        result["refused"] = True
        result["errno"] = error.errno
        result["errno_name"] = errno_name(error.errno)
        result["detail"] = error.strerror
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["write", "append", "read", "chmod"])
    parser.add_argument("target")
    parser.add_argument("--mode", default="0o600")
    args = parser.parse_args(argv)

    if args.action == "write":
        result = attempt_write(args.target)
    elif args.action == "append":
        result = attempt_write(args.target, mode="append")
    elif args.action == "read":
        result = attempt_read(args.target)
    else:
        try:
            mode = int(args.mode, 8)
        except ValueError:
            print(json.dumps({"error": "bad mode"}))
            return 5
        result = attempt_chmod(args.target, mode)

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    # 0 = the operation went through, 3 = it was refused, 5 = unusable.
    return 3 if result["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
