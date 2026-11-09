"""Tests for the read-only Paperclip export fetcher.

The fetcher must issue GET requests only, keep the API key out of the output
and out of the export document, derive the company and the platform build
from the platform's own responses, and fail closed when the platform answers
with something other than the expected shape.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "fetch_paperclip.py"

ISSUE = {
    "id": "issue-example-1",
    "identifier": "APO-EXAMPLE",
    "companyId": "company-example-1",
    "assigneeAgentId": "agent-id-producer",
    "responsibleUserId": "user-id-owner",
}
COMMENT = {
    "id": "comment-example-1",
    "authorType": "agent",
    "authorAgentId": "agent-id-verifier",
    "authorUserId": None,
    "onBehalfOfUserId": None,
    "createdByRunId": "run-example-1",
    "createdAt": "2026-11-09T00:00:00.000Z",
    "deletedAt": None,
    "companyId": "company-example-1",
    "body": "## 预审结论\n建议合并\n",
}
HEALTH = {"status": "ok", "version": "example-build-1"}


class FakePlatform:
    """A tiny stand-in that answers the GET routes the fetcher uses."""

    def __init__(self, issue=ISSUE, comments=(COMMENT,), status=200, health=HEALTH):
        self.issue = issue
        self.comments = list(comments)
        self.status = status
        self.health = health
        self.paths = []
        self.methods = []

    def __call__(self, handler):
        path = handler.path
        self.paths.append(path)
        if path.endswith("/health"):
            return _Response(self.status, json.dumps(self.health))
        if path.endswith("/issues/issue-example-1"):
            return _Response(self.status, json.dumps(self.issue))
        if path.endswith("/issues/issue-example-1/comments"):
            return _Response(self.status, json.dumps(self.comments))
        return _Response(404, json.dumps({"error": "not found"}))


class _Response:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload.encode("utf-8")

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def load_module():
    sys.path.insert(0, str(ROOT))
    try:
        import fetch_paperclip
        return fetch_paperclip
    finally:
        sys.path.pop(0)


class BuildExport(unittest.TestCase):
    def test_export_has_the_frozen_shape(self):
        fetch_paperclip = load_module()
        export = fetch_paperclip.build_export(
            ISSUE, COMMENT, "paperclip", "example-instance", "example-build-1")
        self.assertEqual(export["schema_version"], "message-export/v1")
        self.assertEqual(set(export),
                         {"schema_version", "adapter", "instance_id", "company_id",
                          "platform_build", "issue", "message"})
        self.assertEqual(set(export["issue"]),
                         {"id", "identifier", "assignee_agent_id", "responsible_user_id"})
        self.assertEqual(set(export["message"]),
                         {"id", "author_type", "author_agent_id", "author_user_id",
                          "on_behalf_of_user_id", "created_by_run_id", "created_at",
                          "deleted_at", "body"})
        self.assertNotIn("result", export)

    def test_company_is_taken_from_the_platform_not_the_caller(self):
        fetch_paperclip = load_module()
        export = fetch_paperclip.build_export(
            ISSUE, COMMENT, "paperclip", "example-instance", "example-build-1")
        self.assertEqual(export["company_id"], "company-example-1")

    def test_a_caller_naming_another_company_is_refused(self):
        fetch_paperclip = load_module()
        with self.assertRaises(fetch_paperclip.PlatformError):
            fetch_paperclip.build_export(
                ISSUE, COMMENT, "paperclip", "example-instance", "example-build-1",
                "company-example-2")

    def test_issue_and_comment_from_different_companies_are_refused(self):
        fetch_paperclip = load_module()
        comment = dict(COMMENT, companyId="company-example-2")
        with self.assertRaises(fetch_paperclip.PlatformError):
            fetch_paperclip.build_export(
                ISSUE, comment, "paperclip", "example-instance", "example-build-1")

    def test_export_refuses_an_oversize_body(self):
        fetch_paperclip = load_module()
        comment = dict(COMMENT, body="x" * (256 * 1024 + 1))
        with self.assertRaises(fetch_paperclip.PlatformError):
            fetch_paperclip.build_export(
                ISSUE, comment, "paperclip", "example-instance", "example-build-1")

    def test_platform_build_comes_from_health_not_the_caller(self):
        # The build id is read from the platform's own /health route.
        fetch_paperclip = load_module()
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('f"{base_url}/health"', source)
        self.assertNotIn("--platform-build", source)


class Cli(unittest.TestCase):
    def run_fetch(self, platform, *args, env=None, api_key="secret-key", extra=()):
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                response = platform(self)
                self.send_response(response.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response.payload)))
                self.end_headers()
                self.wfile.write(response.payload)

            def do_POST(self):
                # The fetcher must never mutate the platform. Record and refuse.
                platform.methods.append("POST")
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_PATCH(self):
                platform.methods.append("PATCH")
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_DELETE(self):
                platform.methods.append("DELETE")
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                out = Path(folder) / "export.json"
                environment = dict(os.environ)
                environment["PAPERCLIP_API_KEY"] = api_key
                if env:
                    environment.update(env)
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), "--base-url",
                     f"http://127.0.0.1:{server.server_port}/api",
                     "--issue-id", "issue-example-1", "--comment-id", "comment-example-1",
                     "--adapter", "paperclip", "--instance-id", "example-instance",
                     "--out", str(out), *extra, *args],
                    capture_output=True, timeout=30, env=environment)
                payload = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
                return proc, payload, platform
        finally:
            server.shutdown()
            server.server_close()

    def test_fetch_writes_a_valid_export_without_leaking_the_key(self):
        platform = FakePlatform()
        proc, payload, platform = self.run_fetch(platform)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["schema_version"], "message-export/v1")
        self.assertEqual(payload["message"]["id"], "comment-example-1")
        self.assertEqual(payload["message"]["author_type"], "agent")
        self.assertEqual(payload["company_id"], "company-example-1")
        self.assertEqual(payload["platform_build"], "example-build-1")
        blob = proc.stdout + proc.stderr + json.dumps(payload).encode()
        self.assertNotIn(b"secret-key", blob)
        # Read-only: every request is a GET.
        self.assertEqual(platform.methods, [])

    def test_a_caller_naming_another_company_is_refused(self):
        platform = FakePlatform()
        proc, payload, _ = self.run_fetch(platform, extra=("--company-id", "company-example-2"))
        self.assertEqual(proc.returncode, 5)
        self.assertIsNone(payload)
        self.assertEqual(json.loads(proc.stdout)["result"], "INPUT_ERROR")

    def test_missing_comment_is_input_error(self):
        platform = FakePlatform(comments=[])
        proc, payload, _ = self.run_fetch(platform)
        self.assertEqual(proc.returncode, 5)
        self.assertIsNone(payload)
        self.assertEqual(json.loads(proc.stdout)["result"], "INPUT_ERROR")

    def test_platform_error_is_input_error(self):
        platform = FakePlatform(status=500)
        proc, payload, _ = self.run_fetch(platform)
        self.assertEqual(proc.returncode, 5)
        self.assertIsNone(payload)

    def test_missing_api_key_is_input_error(self):
        platform = FakePlatform()
        proc, payload, _ = self.run_fetch(platform, api_key="")
        self.assertEqual(proc.returncode, 5)
        self.assertIsNone(payload)
        self.assertEqual(json.loads(proc.stdout)["result"], "INPUT_ERROR")

    def test_comment_missing_machine_fields_is_input_error(self):
        comment = {k: v for k, v in COMMENT.items() if k != "authorAgentId"}
        platform = FakePlatform(comments=(comment,))
        proc, payload, _ = self.run_fetch(platform)
        self.assertEqual(proc.returncode, 5)
        self.assertIsNone(payload)

    def test_health_without_a_version_is_input_error(self):
        platform = FakePlatform(health={"status": "ok"})
        proc, payload, _ = self.run_fetch(platform)
        self.assertEqual(proc.returncode, 5)
        self.assertIsNone(payload)


if __name__ == "__main__":
    unittest.main()
