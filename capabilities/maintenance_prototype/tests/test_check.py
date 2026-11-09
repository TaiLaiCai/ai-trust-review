import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(BASE, "check.py")
EXAMPLE = os.path.join(BASE, "example", "prototype.json")
REPO_ROOT = os.path.abspath(os.path.join(BASE, "..", "..", ".."))


def run_check(path):
    return subprocess.run([sys.executable, CHECK, path], capture_output=True, text=True)


def load_example():
    with open(EXAMPLE, encoding="utf-8") as f:
        return json.load(f)


def write_tmp(doc):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return path


class ContractTests(unittest.TestCase):
    def test_example_passes(self):
        r = run_check(EXAMPLE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["verdict"], "PASS")
        self.assertEqual(out["scope"], "document-and-boundary-only")
        self.assertEqual(out["counterexamples"], 4)

    def test_wrong_schema_version(self):
        doc = load_example()
        doc["schema_version"] = "maintenance-prototype/v2"
        r = run_check(write_tmp(doc))
        self.assertEqual(r.returncode, 2)

    def test_not_exactly_four_counterexamples(self):
        doc = load_example()
        doc["counterexamples"] = doc["counterexamples"][:3]
        self.assertEqual(run_check(write_tmp(doc)).returncode, 2)

    def test_unknown_field_rejected(self):
        doc = load_example()
        doc["extra"] = 1
        self.assertEqual(run_check(write_tmp(doc)).returncode, 2)

    def test_duplicate_json_key_rejected(self):
        with open(EXAMPLE, encoding="utf-8") as f:
            raw = f.read()
        raw = raw.replace("{\n \"schema_version\"", "{\"schema_version\": \"x\",\n \"schema_version\"", 1)
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
        self.assertEqual(run_check(path).returncode, 2)

    def test_red_with_zero_exit_rejected(self):
        doc = load_example()
        doc["counterexamples"][0]["red"]["exit_code"] = 0
        self.assertEqual(run_check(write_tmp(doc)).returncode, 2)

    def test_green_with_nonzero_exit_rejected(self):
        doc = load_example()
        doc["counterexamples"][1]["green"]["exit_code"] = 1
        self.assertEqual(run_check(write_tmp(doc)).returncode, 2)

    def test_missing_red_or_green_rejected(self):
        doc = load_example()
        del doc["counterexamples"][2]["red"]
        self.assertEqual(run_check(write_tmp(doc)).returncode, 2)

    def test_bad_digest_rejected(self):
        doc = load_example()
        doc["counterexamples"][0]["green"]["stdout_sha256"] = "ZZ" + "0" * 62
        self.assertEqual(run_check(write_tmp(doc)).returncode, 2)

    def test_incident_unknown_counterexample_rejected(self):
        doc = load_example()
        doc["incidents"][0]["counterexample"] = "no-such-hazard"
        self.assertEqual(run_check(write_tmp(doc)).returncode, 2)

    def test_relative_retention_repo_rejected(self):
        doc = load_example()
        doc["retention"]["repo"] = "../retention.git"
        self.assertEqual(run_check(write_tmp(doc)).returncode, 2)


class BoundaryTests(unittest.TestCase):
    def test_retention_repo_inside_working_repo_rejected(self):
        doc = load_example()
        doc["retention"]["repo"] = os.path.join(REPO_ROOT, "retention.git")
        r = run_check(write_tmp(doc))
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_no_retention_directory_in_repo(self):
        for dirpath, dirnames, _ in os.walk(REPO_ROOT):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            self.assertNotIn("retention", dirnames, dirpath)


class RealAssertionTests(unittest.TestCase):
    """红绿两端真实断言：复跑 example 回执里的命令，核对退出码与字节摘要。"""

    def receipts(self):
        doc = load_example()
        items = []
        for cx in doc["counterexamples"]:
            items.append(("red", cx["red"]))
            items.append(("green", cx["green"]))
        for inc in doc["incidents"]:
            items.append(("incident-green", inc["green"]))
        return items

    def test_red_really_fails_and_green_really_passes(self):
        for kind, receipt in self.receipts():
            p = subprocess.run(receipt["argv"], capture_output=True, cwd=os.path.join(BASE, "example"))
            if kind == "red":
                self.assertNotEqual(p.returncode, 0, receipt["argv"])
            else:
                self.assertEqual(p.returncode, 0, receipt["argv"])
            self.assertEqual(hashlib.sha256(p.stdout).hexdigest(), receipt["stdout_sha256"],
                             "%s stdout digest" % kind)
            self.assertEqual(hashlib.sha256(p.stderr).hexdigest(), receipt["stderr_sha256"],
                             "%s stderr digest" % kind)

    def test_document_bytes_stable(self):
        # 文档自恰：example 原样可再通过检查（防止手改文档后未复跑）
        self.assertEqual(run_check(EXAMPLE).returncode, 0)


if __name__ == "__main__":
    unittest.main()
