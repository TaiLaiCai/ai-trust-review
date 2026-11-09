#!/usr/bin/env python3
"""Read-only Paperclip export for the C4 identity adapter.

Fetches one issue and one of its comments through the platform API and writes
the frozen `message-export/v1` document. Read-only: only GET requests, and the
API key is read from the environment and never written to disk or printed.

What the platform must prove, and what the caller may not assert:

  * `company_id` is taken from the platform's own objects (the issue and the
    comment each carry `companyId`). A caller-supplied `--company-id` is only
    a cross-check: if it disagrees with the platform, the export is refused.
  * `platform_build` is taken from the platform's own `/health` version.
  * `instance_id` is an operator-declared scope label. The platform API
    exposes no instance identifier, so this value is NOT platform-proven. It
    only separates scopes and must agree between config and export; no trust
    decision rests on it.

Exit codes:
  0 the export was written
  2 usage error
  5 platform error, missing comment, or a response that is not the expected shape
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

VERSION = "v1"
EXPORT_SCHEMA = "message-export/v1"
MAX_BODY_BYTES = 256 * 1024
DEFAULT_BASE_URL = "http://127.0.0.1:3100/api"
TIMEOUT_SECONDS = 30

REQUIRED_MESSAGE_FIELDS = ("id", "authorType", "authorAgentId", "authorUserId",
                            "onBehalfOfUserId", "createdByRunId", "createdAt",
                            "deletedAt", "body")
REQUIRED_ISSUE_FIELDS = ("id", "identifier", "assigneeAgentId", "responsibleUserId")


class PlatformError(RuntimeError):
    pass


def _get(url, api_key, timeout=TIMEOUT_SECONDS):
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise PlatformError(f"platform returned HTTP {error.code} for {url}") from None
    except urllib.error.URLError as error:
        raise PlatformError(f"platform unreachable: {error.reason}") from None
    except TimeoutError:
        raise PlatformError("platform request timed out") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise PlatformError(f"platform response is not JSON: {type(error).__name__}") from None


def fetch_platform_build(base_url, api_key):
    """The platform's own build id. Never taken from the caller."""
    payload = _get(f"{base_url}/health", api_key)
    if not isinstance(payload, dict):
        raise PlatformError("health response is not an object")
    build = payload.get("version")
    if not isinstance(build, str) or not build.strip():
        raise PlatformError("health response lacks a version")
    return build.strip()


def fetch_issue(base_url, api_key, issue_id):
    payload = _get(f"{base_url}/issues/{issue_id}", api_key)
    if not isinstance(payload, dict):
        raise PlatformError("issue response is not an object")
    for field in REQUIRED_ISSUE_FIELDS:
        if field not in payload:
            raise PlatformError(f"issue response lacks {field}")
    company_id = payload.get("companyId")
    if not isinstance(company_id, str) or not company_id.strip():
        raise PlatformError("issue response lacks companyId")
    return payload


def fetch_comment(base_url, api_key, issue_id, comment_id):
    payload = _get(f"{base_url}/issues/{issue_id}/comments", api_key)
    if not isinstance(payload, list):
        raise PlatformError("comments response is not a list")
    for comment in payload:
        if isinstance(comment, dict) and comment.get("id") == comment_id:
            for field in REQUIRED_MESSAGE_FIELDS:
                if field not in comment:
                    raise PlatformError(f"comment response lacks {field}")
            return comment
    raise PlatformError(f"comment {comment_id} not found on issue {issue_id}")


def build_export(issue, comment, adapter, instance_id, platform_build, company_id=None,
                 result=None):
    """Assemble the frozen export. `company_id` is platform-derived."""
    body = comment.get("body")
    if not isinstance(body, str):
        raise PlatformError("comment body is not a string")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise PlatformError("comment body exceeds size limit")

    issue_company = issue.get("companyId")
    comment_company = comment.get("companyId")
    if not isinstance(comment_company, str) or not comment_company.strip():
        raise PlatformError("comment response lacks companyId")
    if comment_company != issue_company:
        raise PlatformError(
            "issue and comment report different companies: "
            f"{issue_company!r} and {comment_company!r}")
    if company_id is not None and company_id != issue_company:
        raise PlatformError(
            f"requested company {company_id!r} differs from the platform's {issue_company!r}")

    export = {
        "schema_version": EXPORT_SCHEMA,
        "adapter": adapter,
        "instance_id": instance_id,
        "company_id": issue_company,
        "platform_build": platform_build,
        "issue": {
            "id": issue["id"],
            "identifier": issue["identifier"],
            "assignee_agent_id": issue.get("assigneeAgentId"),
            "responsible_user_id": issue.get("responsibleUserId"),
        },
        "message": {
            "id": comment["id"],
            "author_type": comment["authorType"],
            "author_agent_id": comment.get("authorAgentId"),
            "author_user_id": comment.get("authorUserId"),
            "on_behalf_of_user_id": comment.get("onBehalfOfUserId"),
            "created_by_run_id": comment.get("createdByRunId"),
            "created_at": comment["createdAt"],
            "deleted_at": comment.get("deletedAt"),
            "body": body,
        },
    }
    if result is not None:
        export["result"] = result
    return export


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="store_true",
                        help="print version and the sha256 of this file, then exit 0")
    parser.add_argument("--base-url", default=os.environ.get("PAPERCLIP_API_URL", DEFAULT_BASE_URL),
                        help="platform API base URL (default: $PAPERCLIP_API_URL)")
    parser.add_argument("--issue-id", required=True)
    parser.add_argument("--comment-id", required=True)
    parser.add_argument("--adapter", required=True, help="adapter name recorded in the export")
    parser.add_argument("--instance-id", required=True,
                        help="operator-declared scope label; the platform exposes no instance id")
    parser.add_argument("--company-id",
                        help="optional cross-check; the platform's own companyId always wins")
    parser.add_argument("--out", required=True, help="path of the export document to write")
    parser.add_argument("--result", help="optional JSON file with capability_scope, "
                                         "artifact_manifest_sha256 and versions")
    args = parser.parse_args(argv)
    if args.version:
        with open(__file__, "rb") as handle:
            print(f"{VERSION} {hashlib.sha256(handle.read()).hexdigest()}")
        return 0

    api_key = os.environ.get("PAPERCLIP_API_KEY")
    if not api_key:
        print(json.dumps({"result": "INPUT_ERROR", "reason": "PAPERCLIP_API_KEY is not set"}))
        return 5
    base_url = args.base_url.rstrip("/")
    if not base_url.endswith("/api"):
        base_url += "/api"
    try:
        platform_build = fetch_platform_build(base_url, api_key)
        issue = fetch_issue(base_url, api_key, args.issue_id)
        comment = fetch_comment(base_url, api_key, args.issue_id, args.comment_id)
        result = None
        if args.result:
            with open(args.result, "rb") as handle:
                result = json.loads(handle.read().decode("utf-8"))
        export = build_export(issue, comment, args.adapter, args.instance_id,
                              platform_build, args.company_id, result)
        payload = (json.dumps(export, ensure_ascii=False, sort_keys=True, indent=2)
                   + "\n").encode("utf-8")
        with open(args.out, "wb") as handle:
            handle.write(payload)
    except PlatformError as error:
        print(json.dumps({"result": "INPUT_ERROR", "reason": str(error)}, ensure_ascii=False))
        return 5
    except (OSError, ValueError, UnicodeDecodeError) as error:
        print(json.dumps({"result": "INPUT_ERROR", "reason": f"{type(error).__name__}: {error}"},
                         ensure_ascii=False))
        return 5
    print(json.dumps({"result": "OK", "out": args.out,
                      "sha256": hashlib.sha256(payload).hexdigest(),
                      "message_id": export["message"]["id"],
                      "author_type": export["message"]["author_type"],
                      "company_id": export["company_id"],
                      "platform_build": export["platform_build"]},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
