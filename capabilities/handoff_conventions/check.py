#!/usr/bin/env python3
"""Lexical handoff convention check; does not authorize or execute a task."""
import argparse
import json
from pathlib import Path
import sys

MAX_BYTES = 256 * 1024
PREFIX = "约定定义："
SCOPE = "lexical-only; not authorization, identity or semantic verification"


class InputError(ValueError):
    pass


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON key")
        result[key] = value
    return result


def parse(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, RecursionError):
        raise InputError("invalid or duplicate-key JSON") from None


def read(stream):
    raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise InputError("input exceeds 256 KiB")
    return raw.decode("utf-8")


def load_terms(raw):
    terms = parse(raw)
    if not isinstance(terms, list) or not terms or any(
            not isinstance(t, str) or not t.strip() or t != t.strip() for t in terms):
        raise InputError("terms must be a non-empty list of trimmed strings")
    if len(set(terms)) != len(terms):
        raise InputError("duplicate convention term")
    return terms


def check(text, terms):
    definitions, body = {}, []
    seen = False
    for line in text.splitlines():
        if line.lstrip().startswith(PREFIX):
            if seen:
                raise InputError("multiple definition lines")
            seen = True
            definitions = parse(line.lstrip()[len(PREFIX):])
            if not isinstance(definitions, dict) or any(
                    key not in terms or not isinstance(value, str) for key, value in definitions.items()):
                raise InputError("definitions must map configured terms to strings")
        else:
            body.append(line)
    body = "\n".join(body)
    missing = [term for term in terms if term in body and (
        not definitions.get(term, "").strip() or
        any(t in definitions.get(term, "") for t in terms))]
    if missing:
        return 3, {"verdict": "NEEDS_CLARIFICATION", "undefined": missing,
                   "next": "不开工；复述缺少明确约定的词，向发件人回问", "scope": SCOPE}
    return 0, {"verdict": "LEXICAL_CLEAR", "next": "继续其他开工检查", "scope": SCOPE}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--terms", type=Path, default=Path(__file__).with_name("terms.json"))
    p.add_argument("handoff", nargs="?", default="-")
    args = p.parse_args(argv)
    try:
        with args.terms.open("rb") as f:
            terms = load_terms(read(f))
        if args.handoff == "-":
            text = read(sys.stdin.buffer)
        else:
            with open(args.handoff, "rb") as f:
                text = read(f)
        code, result = check(text, terms)
    except (InputError, UnicodeDecodeError, OSError) as error:
        code, result = 5, {"verdict": "INPUT_ERROR", "reason": str(error),
                           "next": "不开工；修正输入或配置后重新检查"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
