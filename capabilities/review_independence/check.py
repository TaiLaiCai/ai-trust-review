#!/usr/bin/env python3
"""Review-independence gate: read-only check, does not authenticate or approve.

Given a PR author (and optional producers) plus the PR's current head SHA,
verify that every declared rerun receipt was produced by a non-author and is
bound to that exact head. This mirrors AGENTS.md; it does not touch the
GitHub ruleset and does not grant any trust.

The `reviews` subcommand is the platform-authenticated path: it consumes the
GitHub PR Review API response (fetched by CI with the workflow token) and
requires that some non-author's latest review on that PR is APPROVED and was
submitted at exactly the current head commit (`commit_id`). Platform reviews
cannot be written into the reviewed tree, so they do not expire themselves
(P1) and the reviewer identity is not a self-declared field (P2).
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
    if not isinstance(pr_author, str) or not pr_author.strip():
        return 2, "USAGE", ["--pr-author must be a non-blank string"]
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


def _usage_guard(pr_author, pr_head_sha):
    if not SHA_RE.match(pr_head_sha or ""):
        return ["--pr-head-sha must be 40 lowercase hex chars"]
    if not isinstance(pr_author, str) or not pr_author.strip():
        return ["--pr-author must be a non-blank string"]
    return []


def check_reviews(pr_author, pr_head_sha, producers, path):
    """Gate on the GitHub PR Review API payload (platform-authenticated).

    Qualifying review = latest review of some non-author/producer user whose
    state is APPROVED and whose commit_id equals the PR's current head.
    Anything less is insufficient and fails closed (exit 1), never PASS.
    """
    usage = _usage_guard(pr_author, pr_head_sha)
    if usage:
        return 2, "USAGE", usage
    try:
        with open(path, "rb") as handle:
            payload = json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return 1, "REVIEW_INDEPENDENCE_VIOLATION", [
            "%s: reviews payload unreadable or invalid JSON (%s) (insufficient, not PASS)"
            % (path, exc)
        ]
    if not isinstance(payload, list):
        return 1, "REVIEW_INDEPENDENCE_VIOLATION", [
            "%s: reviews payload must be a JSON list (insufficient, not PASS)" % path
        ]
    forbidden = {a.strip().lower() for a in [pr_author] + list(producers) if a and a.strip()}
    latest = {}
    malformed = []
    for item in payload:
        if not isinstance(item, dict):
            malformed.append("non-object entry in reviews payload")
            continue
        user = item.get("user")
        login = user.get("login") if isinstance(user, dict) else None
        state = item.get("state")
        commit = item.get("commit_id")
        stamp = item.get("submitted_at") or ""
        if not isinstance(login, str) or not login.strip() or not isinstance(state, str):
            malformed.append("review entry missing user.login/state (insufficient, not PASS)")
            continue
        key = login.strip().lower()
        prev = latest.get(key)
        if prev is None or str(stamp) >= str(prev.get("submitted_at") or ""):
            latest[key] = {"login": login, "state": state, "commit_id": commit,
                           "submitted_at": stamp}
    problems = list(malformed)
    qualified = []
    for key, rev in sorted(latest.items()):
        if key in forbidden:
            if rev["state"] == "APPROVED":
                problems.append("self-review APPROVED by %r equals PR author/producer (ignored)"
                                % rev["login"])
            continue
        if rev["state"] != "APPROVED":
            problems.append("latest review by %s is %s, not APPROVED" % (rev["login"], rev["state"]))
        elif rev["commit_id"] != pr_head_sha:
            problems.append("APPROVED by %s is bound to stale commit %s != PR head %s"
                            % (rev["login"], rev["commit_id"], pr_head_sha))
        else:
            qualified.append(rev["login"])
    if not qualified:
        problems.insert(0, "no platform-authenticated non-author APPROVED review bound to "
                           "head %s; failing closed (NOT_TESTED stays red, never PASS)"
                        % pr_head_sha)
        return 1, "REVIEW_INDEPENDENCE_VIOLATION", problems
    return 0, "INDEPENDENT_AND_HEAD_BOUND", [
        "latest APPROVED by non-author(s) %s bound to head %s" % (", ".join(qualified), pr_head_sha)
    ]


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
    rev = sub.add_parser("reviews", help="gate on the GitHub PR Review API payload")
    rev.add_argument("--pr-author", required=True)
    rev.add_argument("--pr-head-sha", required=True)
    rev.add_argument("--producer", action="append", default=[],
                     help="additional producer identity (repeatable)")
    rev.add_argument("--reviews-file", required=True,
                     help="JSON list from GET /repos/{repo}/pulls/{n}/reviews")
    args = parser.parse_args(argv)
    if args.version:
        print("review-independence/v1")
        return 0
    if not args.cmd:
        parser.error("the following arguments are required: cmd")
    code, verdict, findings = check(args.pr_author, args.pr_head_sha, args.producer, args.receipt) \
        if args.cmd == "check" else check_reviews(args.pr_author, args.pr_head_sha,
                                                  args.producer, args.reviews_file)
    print(json.dumps({"verdict": verdict, "findings": findings}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
