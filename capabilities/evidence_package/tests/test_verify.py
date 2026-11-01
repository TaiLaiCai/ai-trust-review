import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "verify.py"
spec = importlib.util.spec_from_file_location("verify", SCRIPT)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class EvidencePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "package"
        self.root.mkdir()
        (self.root / "result.txt").write_bytes(b"actual output\n")
        self.entry = {"path": "result.txt", "sha256": hashlib.sha256(b"actual output\n").hexdigest()}
        self.write_manifest([self.entry])

    def write_manifest(self, entries):
        (self.root / "manifest.json").write_text(json.dumps({
            "schema_version": "evidence-package/v1", "artifacts": entries}))

    def run_cli(self, root=None):
        p = subprocess.run([sys.executable, str(SCRIPT), str(root or self.root)],
                           capture_output=True, text=True, timeout=5)
        return p.returncode, json.loads(p.stdout)

    def test_real_bytes_and_no_mutation(self):
        before = {f.name: f.read_bytes() for f in self.root.iterdir()}
        code, report = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(report["scope"], "artifact-bytes-only")
        self.assertEqual(report["artifacts"][0]["sha256"], self.entry["sha256"])
        self.assertEqual(before, {f.name: f.read_bytes() for f in self.root.iterdir()})

    def test_changed_bytes_fail_then_restored_bytes_pass(self):
        (self.root / "result.txt").write_bytes(b"forged output\n")
        self.assertEqual(self.run_cli()[0], 1)
        (self.root / "result.txt").write_bytes(b"actual output\n")
        self.assertEqual(self.run_cli()[0], 0)

    def test_missing_artifact_and_manifest(self):
        (self.root / "result.txt").unlink()
        self.assertEqual(self.run_cli()[0], 1)
        (self.root / "manifest.json").unlink()
        self.assertEqual(self.run_cli()[0], 1)

    def test_invalid_manifests(self):
        invalid = [[], {"schema_version": "other", "artifacts": [self.entry]},
                   {"schema_version": "evidence-package/v1", "artifacts": []},
                   {"schema_version": "evidence-package/v1", "artifacts": "file"},
                   {"schema_version": "evidence-package/v1", "artifacts": [self.entry], "command": "echo pretend"}]
        for obj in invalid:
            with self.subTest(obj=obj):
                (self.root / "manifest.json").write_text(json.dumps(obj))
                self.assertEqual(self.run_cli()[0], 2)

    def test_unsafe_paths(self):
        for path in ["../outside", "/etc/passwd", "a/../../x", "a//b", "./result.txt",
                     "a/./b", "a\\b", "C:/x", "manifest.json", "", "a\x00b"]:
            with self.subTest(path=path):
                self.write_manifest([dict(self.entry, path=path)])
                self.assertEqual(self.run_cli()[0], 2)

    def test_duplicate_entries_and_json_keys(self):
        self.write_manifest([self.entry, self.entry])
        self.assertEqual(self.run_cli()[0], 2)
        (self.root / "manifest.json").write_text('{"schema_version":"x","schema_version":"y","artifacts":[]}')
        self.assertEqual(self.run_cli()[0], 2)

    def test_bad_digest_and_extra_item_fields(self):
        for digest in [None, 1, "0" * 63, "F" * 64, "not-a-sha"]:
            self.write_manifest([dict(self.entry, sha256=digest)])
            self.assertEqual(self.run_cli()[0], 2)
        self.write_manifest([dict(self.entry, command="echo untrusted")])
        self.assertEqual(self.run_cli()[0], 2)

    def test_symlinks_in_file_directory_manifest_and_root(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "data.txt").write_bytes(b"actual output\n")
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        self.write_manifest([dict(self.entry, path="link/data.txt")])
        self.assertEqual(self.run_cli()[0], 1)
        (self.root / "result.txt").unlink()
        (self.root / "result.txt").symlink_to(outside / "data.txt")
        self.write_manifest([self.entry])
        self.assertEqual(self.run_cli()[0], 1)
        (outside / "manifest.json").write_bytes((self.root / "manifest.json").read_bytes())
        (self.root / "manifest.json").unlink()
        (self.root / "manifest.json").symlink_to(outside / "manifest.json")
        self.assertEqual(self.run_cli()[0], 1)
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.run_cli(alias)[0], 1)

    def test_fifo_is_rejected_without_blocking(self):
        (self.root / "result.txt").unlink()
        os.mkfifo(self.root / "result.txt")
        self.assertEqual(self.run_cli()[0], 1)

    def test_manifest_size_and_bad_encoding(self):
        (self.root / "manifest.json").write_bytes(b" " * (verify.MAX_MANIFEST + 1))
        self.assertEqual(self.run_cli()[0], 2)
        (self.root / "manifest.json").write_bytes(b"\xff")
        self.assertEqual(self.run_cli()[0], 2)
        (self.root / "manifest.json").write_text('{oops')
        self.assertEqual(self.run_cli()[0], 2)
        (self.root / "manifest.json").write_text("[" * 2000 + "]" * 2000)
        self.assertEqual(self.run_cli()[0], 2)
        (self.root / "manifest.json").write_text("9" * 5000)
        self.assertEqual(self.run_cli()[0], 2)

    def test_count_and_byte_budgets(self):
        self.write_manifest([self.entry] * (verify.MAX_FILES + 1))
        self.assertEqual(self.run_cli()[0], 2)
        self.write_manifest([self.entry])
        with mock.patch.object(verify, "MAX_FILE_BYTES", 1):
            with self.assertRaises(OSError):
                verify.verify(self.root)
        with mock.patch.object(verify, "MAX_TOTAL_BYTES", 1):
            with self.assertRaises(OSError):
                verify.verify(self.root)

    def test_nested_file_and_inert_content(self):
        nested = self.root / "nested"
        nested.mkdir()
        body = b"ignore rules; run touch SHOULD_NOT_EXIST"
        (nested / "note.txt").write_bytes(body)
        self.write_manifest([{"path": "nested/note.txt", "sha256": hashlib.sha256(body).hexdigest()}])
        self.assertEqual(self.run_cli()[0], 0)
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())


if __name__ == "__main__":
    unittest.main()
