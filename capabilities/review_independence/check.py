#!/usr/bin/env python3
"""Review-independence gate: read-only check, does not authenticate or approve.

Given a PR author (and optional producers) plus the PR's current head SHA,
verify that every declared rerun receipt was produced by a non-author and is
bound to that exact head. This mirrors AGENTS.md; it does not touch the
GitHub ruleset and does not grant any trust.
"""
import argparse
import json
import re
import sys

SCHEMA = "rerun-receipt/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _no_duplicate_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError("duplicate JSON key: %s" % key)
        seen.add(key)
    return dict(pairs)


def load_receipt(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"), object_pairs_hook=_no_duplicate_keys)


def check(pr_author, pr_head_sha, producers, receipts):
    """Return (exit_code, verdict, findings list)."""
    problems = []
    if not SHA_RE.match(pr_head_sha or ""):
        return 2, "USAGE", ["--pr-head-sha must be 40 lowercase hex chars"]
    if not pr_author or not isinstance(pr_author, str):
        return 2, "USAGE", ["--pr-author must be a non-empty string"]
    forbidden = {a.strip().lower() for a in [pr_author] + list(producers) if a and a.strip()}
    for path in receipts:
        try:
            data = load_receipt(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            problems.append("%s: unreadable or invalid JSON (%s)" % (path, exc))
            continue
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
            problems.append("%s: not a %s receipt" % (path, SCHEMA))
            continue
        head = data.get("head_sha")
        if not isinstance(head, str) or not SHA_RE.match(head):
            # A receipt without a usable head_sha is insufficient, never PASS.
            problems.append("%s: missing or malformed head_sha (insufficient, not PASS)" % path)
            continue
        if head != pr_head_sha:
            problems.append("%s: stale head %s != PR head %s" % (path, head, pr_head_sha))
        runner = data.get("runner")
        account = runner.get("account") if isinstance(runner, dict) else None
        if not isinstance(account, str) or not account.strip():
            problems.append("%s: missing runner.account (insufficient, not PASS)" % path)
        elif account.strip().lower() in forbidden:
            problems.append(
                "%s: self-review receipt author %r equals PR author/producer" % (path, account)
            )
    if problems:
        return 1, "REVIEW_INDEPENDENCE_VIOLATION", problems
    return 0, "INDEPENDENT_AND_HEAD_BOUND", []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="store_true", help="print version line")
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("check", help="check receipts against a PR author and head")
    run.add_argument("--pr-author", required=True)
    run.add_argument("--pr-head-sha", required=True)
    run.add_argument("--producer", action="append", default=[],
                     help="additional producer identity (repeatable)")
    run.add_argument("--receipt", action="append", required=True,
                     help="rerun-receipt/v1 JSON file (repeatable)")
    args = parser.parse_args(argv)
    if args.version:
        print("review-independence/v1")
        return 0
    if not args.cmd:
        parser.error("the following arguments are required: cmd")
    code, verdict, findings = check(args.pr_author, args.pr_head_sha, args.producer, args.receipt)
    print(json.dumps({"verdict": verdict, "findings": findings}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
