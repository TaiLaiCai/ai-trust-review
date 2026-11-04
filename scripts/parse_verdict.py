#!/usr/bin/env python3
"""Extract the single pre-review verdict line. This does not approve or grade."""
import sys
from pathlib import Path

VERDICTS = ("建议合并", "需修改", "阻塞")
PREFIX = "VERDICT:"


class VerdictError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def parse_verdict(text):
    found = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(PREFIX):
            found.append(line[len(PREFIX):].strip())
    if not found:
        raise VerdictError("missing", "no verdict line")
    if len(found) > 1:
        raise VerdictError("multiple", "multiple verdict lines")
    if found[0] not in VERDICTS:
        raise VerdictError("invalid", "invalid verdict")
    return found[0]


def main(argv):
    if len(argv) > 2:
        print("usage: parse_verdict.py [FILE]", file=sys.stderr)
        return 2
    if len(argv) == 2:
        try:
            text = Path(argv[1]).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        text = sys.stdin.read()
    try:
        verdict = parse_verdict(text)
    except VerdictError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
