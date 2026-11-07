import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check.py"
spec = importlib.util.spec_from_file_location("rerun_receipt_check", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

EXIT0 = [sys.executable, "-c", "print('ok')"]
EXIT4 = [sys.executable, "-c", "import sys; sys.exit(4)"]


def git(repo, *argv):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "commit.gpgsign=false", *argv], cwd=str(repo), check=True,
                   capture_output=True, text=True)


class ReRunReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.repo = base / "repo"
        (self.repo / "sub").mkdir(parents=True)
        (self.repo / "sub" / "seed.txt").write_text("seed\n")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "seed")
        self.head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.repo),
                                   capture_output=True, text=True, check=True).stdout.strip()
        self.dir = base / "work"
        self.dir.mkdir()
        self.manifest = self.dir / "manifest.json"
        self.receipts = self.dir / "receipts.json"
        self.evidence = self.dir / "evidence"

    def write_manifest(self, commands):
        self.manifest.write_text(json.dumps({
            "schema_version": "rerun-manifest/v1", "head_sha": self.head,
            "commands": commands}))

    def cli(self, *argv):
        return subprocess.run([sys.executable, str(SCRIPT), *argv],
                              capture_output=True, text=True, timeout=60)

    def emit(self, *extra):
        return self.cli("emit", str(self.manifest), "--repo", str(self.repo),
                        "--runner-account", "tester", *extra)

    def verify(self, *extra):
        return self.cli("verify", str(self.manifest), str(self.receipts), *extra)

    def load_receipts(self):
        return json.loads(self.receipts.read_text())

    def test_emit_verify_roundtrip_and_verify_is_read_only(self):
        self.write_manifest([
            {"id": "a-ok", "argv": EXIT0, "expect_exit": 0},
            {"id": "b-exit4", "argv": EXIT4, "expect_exit": 4},
        ])
        result = self.emit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["verdict"], "PASS")
        self.assertTrue(self.receipts.is_file() and (self.evidence / "a-ok.stdout").is_file())

        before = {p.name: p.read_bytes() for p in self.evidence.iterdir()}
        result = self.verify("--evidence", str(self.evidence))
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["scope"], "receipts-plus-evidence-bytes")
        self.assertEqual(report["head_sha"], self.head)
        self.assertEqual([row["id"] for row in report["checked"]], ["a-ok", "b-exit4"])
        self.assertEqual({p.name: p.read_bytes() for p in self.evidence.iterdir()}, before)

        result = self.verify()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["scope"], "receipts-schema-only")

    def test_emit_expect_mismatch_still_writes_receipts(self):
        self.write_manifest([{"id": "wrong-expect", "argv": EXIT4, "expect_exit": 0}])
        result = self.emit()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["verdict"], "FAIL")
        self.assertEqual(self.load_receipts()["receipts"][0]["exit_code"], 4)
        self.assertEqual(self.verify("--evidence", str(self.evidence)).returncode, 1)

    def test_timeout_is_recorded_not_hidden(self):
        slow = [sys.executable, "-c", "import time; time.sleep(30)"]
        self.write_manifest([{"id": "slow", "argv": slow}])
        result = self.emit("--timeout", "1")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.load_receipts()["receipts"][0]["exit_code"], -9)
        self.assertIn("timeout after", (self.evidence / "slow.stderr").read_text())
        self.assertEqual(self.verify("--evidence", str(self.evidence)).returncode, 0)

    def test_verify_tampered_evidence_fails(self):
        self.write_manifest([{"id": "a-ok", "argv": EXIT0, "expect_exit": 0}])
        self.assertEqual(self.emit().returncode, 0)
        (self.evidence / "a-ok.stdout").write_bytes(b"forged\n")
        self.assertEqual(self.verify("--evidence", str(self.evidence)).returncode, 1)

    def test_verify_tampered_receipt_digest_fails(self):
        self.write_manifest([{"id": "a-ok", "argv": EXIT0, "expect_exit": 0}])
        self.assertEqual(self.emit().returncode, 0)
        document = self.load_receipts()
        document["receipts"][0]["stdout_sha256"] = "0" * 64
        self.receipts.write_text(json.dumps(document))
        self.assertEqual(self.verify("--evidence", str(self.evidence)).returncode, 1)

    def test_verify_argv_extra_and_missing_receipts_fail(self):
        self.write_manifest([{"id": "a-ok", "argv": EXIT0, "expect_exit": 0}])
        self.assertEqual(self.emit().returncode, 0)
        document = self.load_receipts()
        document["receipts"][0]["argv"] = [sys.executable, "-c", "print('forged')"]
        self.receipts.write_text(json.dumps(document))
        self.assertEqual(self.verify().returncode, 1)

        document["receipts"][0]["argv"] = EXIT0
        document["receipts"].append(dict(document["receipts"][0], id="extra"))
        self.receipts.write_text(json.dumps(document))
        self.assertEqual(self.verify().returncode, 1)

        document = self.load_receipts()
        document["receipts"][0]["id"] = "other-id"
        self.receipts.write_text(json.dumps(document))
        self.assertEqual(self.verify().returncode, 1)

        document["receipts"] = []
        self.receipts.write_text(json.dumps(document))
        self.assertEqual(self.verify().returncode, 2)

    def test_verify_missing_evidence_file_fails(self):
        self.write_manifest([{"id": "a-ok", "argv": EXIT0, "expect_exit": 0}])
        self.assertEqual(self.emit().returncode, 0)
        (self.evidence / "a-ok.stderr").unlink()
        self.assertEqual(self.verify("--evidence", str(self.evidence)).returncode, 1)

    def test_contract_violations_exit_2(self):
        self.write_manifest([{"id": "a-ok", "argv": EXIT0, "expect_exit": 0}])
        good = self.receipts.read_text() if self.emit().returncode == 0 else None
        self.assertIsNotNone(good)
        cases = []
        self.manifest.write_text(json.dumps({"schema_version": "other", "head_sha": self.head,
                                             "commands": [{"id": "a", "argv": EXIT0}]}))
        cases.append(self.verify())
        self.write_manifest([{"id": "a-ok", "argv": EXIT0, "expect_exit": True}])
        cases.append(self.verify())
        self.write_manifest([{"id": "UPPER", "argv": EXIT0}])
        cases.append(self.emit())
        document = self.load_receipts()
        document["runner"]["extra"] = "field"
        self.receipts.write_text(json.dumps(document))
        cases.append(self.verify())
        self.receipts.write_text(good[:-2] + ', "unexpected": 1}')
        cases.append(self.verify())
        for result in cases:
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_head_binding_exit_2(self):
        self.write_manifest([{"id": "a-ok", "argv": EXIT0}])
        self.manifest.write_text(self.manifest.read_text().replace(self.head, "0" * 40))
        result = self.emit()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.receipts.exists())

        plain = Path(self.temp.name) / "plain"
        plain.mkdir()
        result = self.cli("emit", str(self.manifest), "--repo", str(plain))
        self.assertEqual(result.returncode, 2)

        self.write_manifest([{"id": "a-ok", "argv": EXIT0}])
        self.assertEqual(self.emit().returncode, 0)
        document = self.load_receipts()
        document["head_sha"] = "1" * 40
        self.receipts.write_text(json.dumps(document))
        self.assertEqual(self.verify().returncode, 2)

    def test_version_fingerprint_locks_own_bytes(self):
        result = self.cli("--version")
        self.assertEqual(result.returncode, 0)
        expected = f"v1 {hashlib.sha256(SCRIPT.read_bytes()).hexdigest()}"
        self.assertEqual(result.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
