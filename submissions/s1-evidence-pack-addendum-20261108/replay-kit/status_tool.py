#!/usr/bin/env python3
"""JSON status summary tool (stdlib only).

Input: JSON array on stdin or via --file. Each element must be an object
with a "status" field whose value is one of:
PASS / FAIL / BLOCKED / NOT_TESTED.

Output: JSON object with counts for the four statuses, printed to stdout.
Exit codes: 0 = success (including empty array), 2 = invalid input.
"""
import argparse
import json
import sys

VALID = ("PASS", "FAIL", "BLOCKED", "NOT_TESTED")


def summarize(items):
    counts = {s: 0 for s in VALID}
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"element {i} is not an object")
        if "status" not in item:
            raise ValueError(f"element {i} missing 'status' field")
        status = item["status"]
        if status not in VALID:
            raise ValueError(f"element {i} has unknown status {status!r}; "
                             f"allowed: {', '.join(VALID)}")
        counts[status] += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="JSON status summary tool")
    parser.add_argument("--file", help="read JSON array from file instead of stdin")
    args = parser.parse_args(argv)

    try:
        raw = open(args.file, "r", encoding="utf-8").read() if args.file else sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("input is not a JSON array")
        print(json.dumps(summarize(data), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
