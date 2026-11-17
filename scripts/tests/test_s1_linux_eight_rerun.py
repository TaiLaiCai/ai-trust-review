"""Synthetic tests for the S1 Linux eight-step helper.

Fixtures in this file are independent and non-sensitive. They are not the
frozen archive, and they do not contain private originals.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "scripts" / "s1-linux-eight-rerun.py"
SPEC = importlib.util.spec_from_file_location("s1_linux_eight_rerun", TOOL_PATH)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

FROZEN_SHA = "551123d9dd8eb8f3e05f0dc2ad8c69207c95db2a19cf524f50988691055538f1"
CANARY = "CANARY-PRIVATE-BYTES-XYZ"
T4 = b"\x01\x02"
T5 = b"leaktest"
T6 = b"0123456789abcdefXYZ"
STATUS_INPUT = b'{"synthetic":1}\n'
STEP_IDS = ["T1", "T2", "T3", "T4", "T5", "T6", "TP", "PREFLIGHT-LOCAL"]

STATUS_TOOL = """\
import sys

def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--file":
        if sys.argv[2] != "status_input.json":
            return 2
        data = open("status_input.json", "rb").read()
    elif len(sys.argv) == 1:
        data = sys.stdin.buffer.read()
    else:
        return 2
    if data.startswith(b"{"):
        sys.stdout.write("synthetic-record\\n")
        return 0
    if len(data) == 2:
        sys.stdout.write("synthetic-short\\n")
        return 0
    sys.stderr.write("synthetic-reject\\n")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
"""

PREFLIGHT_OK = """\
import sys
from pathlib import Path
need = ("status_tool.py", "test_status_tool.py", "sample_fixed.json", "README.md")
if any(not Path(name).is_file() for name in need):
    raise SystemExit(3)
sys.stdout.write("synthetic-preflight-ok\\n")
"""

PREFLIGHT_EXIT3 = "import sys\nraise SystemExit(3)\n"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def unittest_source(count):
    lines = ["import unittest", "", "class Synthetic(unittest.TestCase):"]
    for index in range(1, count + 1):
        lines.append(f"    def test_{index:02d}(self):")
        lines.append("        self.assertEqual(1, 1)")
    lines.append("")
    return "\n".join(lines).encode()


def pack(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, blob in files.items():
            archive.writestr(name, blob)
    return buffer.getvalue()


def core_files(status=None, tests=None, preflight=None, extra=None):
    files = {
        "status_tool.py": (status if status is not None else STATUS_TOOL).encode(),
        "test_status_tool.py": tests if tests is not None else unittest_source(7),
        "test_preflight.py": unittest_source(3),
        "preflight.py": (preflight if preflight is not None else PREFLIGHT_OK).encode(),
        "status_input.json": STATUS_INPUT,
        "sample_fixed.json": b'{"synthetic":"fixture"}\n',
        "README.md": b"synthetic fixture readme\n",
        "notes.txt": (CANARY + "\n").encode(),
    }
    if extra:
        files.update(extra)
    return files


def binding_for(files, fixtures=None):
    if fixtures is None:
        fixtures = {"T4": T4, "T5": T5, "T6": T6}
    return {
        "schema_version": "s1-linux-eight-binding/v0",
        "steps": list(STEP_IDS),
        "members": {name: sha256(blob) for name, blob in files.items()},
        "stdin_fixtures": {
            "T4": {"bytes": 2, "sha256": sha256(fixtures["T4"]), "name": "t4.bin"},
            "T5": {"bytes": 8, "sha256": sha256(fixtures["T5"]), "name": "t5.bin"},
            "T6": {"bytes": 19, "sha256": sha256(fixtures["T6"]), "name": "t6.bin"},
        },
    }


def touch_source(marker, delay=0):
    wait = f"import time\ntime.sleep({delay})\n" if delay else ""
    return (
        "import unittest\n"
        + wait
        + "class Synthetic(unittest.TestCase):\n"
        + "    def test_hold_canary_marker(self):\n"
        + ("        time.sleep(30)\n" if delay else "")
        + f"        open({marker!r}, 'w').write('ran')\n"
    )


def marker_program(marker):
    return f"open({marker!r}, 'w').write('ran')\nimport sys\nraise SystemExit(0)\n"


class S1LinuxEightRerunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "CANARYPATH"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def dirs(self):
        src = self.root / "src"
        out = self.root / "out"
        fix = self.root / "fix"
        for path in (src, out, fix):
            path.mkdir(exist_ok=True)
        return src, out, fix

    def assert_sanitized(self, text, receipt):
        self.assertEqual(receipt["schema_version"], "s1-linux-eight-rerun/v0")
        self.assertNotEqual(receipt["schema_version"], "rerun-receipt/v1")
        self.assertTrue(receipt["not_rerun_receipt_v1"])
        self.assertEqual(receipt["why_not_rerun_receipt_v1"], "no-git-head-binding")
        self.assertEqual(receipt["s1_judgment"], "NOT_TESTED")
        self.assertEqual(receipt["content_expectation"], "NOT_PROVIDED")
        self.assertEqual(receipt["preflight_historical_conflict"], "UNRESOLVED")
        self.assertIs(receipt["preflight_normalized_to_pass"], False)
        self.assertEqual(receipt["lifecycle_vm_key_destruction"], "NOT_IMPLEMENTED")
        self.assertEqual(receipt["hour_limit_24"], "NOT_IMPLEMENTED")
        self.assertIs(receipt["isolation"]["subprocess_is_sandbox"], False)
        self.assertIs(receipt["isolation"]["network_limited_by_this_tool"], False)
        self.assertIs(receipt["isolation"]["filesystem_limited_by_this_tool"], False)
        self.assertEqual(receipt["tool_exit_meaning"], "technical-only")
        for step in receipt["steps"]:
            self.assertEqual(step["s1_step_judgment"], "NOT_TESTED")
            self.assertIs(step["normalized_to_pass"], False)
        for forbidden in (
            CANARY,
            "CANARYPATH",
            "CANARY-ESCAPE",
            "leaktest",
            "synthetic-record",
            "synthetic-reject",
            "synthetic-short",
            "synthetic-preflight-ok",
            "test_hold_canary_marker",
            "YYYYYYYY",
            "Ran ",
            "OK\n",
            "XYZ",
            "/tmp",
            "\\",
            "..",
        ):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertNotIn('"argv"', text)

    def run_main(self, args, identity=None):
        saved = mod.FROZEN
        stdout = io.StringIO()
        try:
            if identity is not None:
                mod.FROZEN = identity
            with contextlib.redirect_stdout(stdout):
                code = mod.main(args)
        finally:
            mod.FROZEN = saved
        text = stdout.getvalue()
        receipt = json.loads(text)
        self.assert_sanitized(text, receipt)
        return code, receipt, text

    def identity_from(self, data):
        measured = mod.measure(data)
        self.assertEqual(measured.public["safety"], "clear", measured.public["safety_reasons"])
        public = measured.public
        return mod.ArchiveIdentity(
            public["sha256"], public["bytes"], public["regular_files"], public["uncompressed_bytes"]
        )

    def prepare(self, files, fixtures=None, fixture_bytes=None):
        _src, out, fix = self.dirs()
        if fixture_bytes is None:
            fixture_bytes = {"t4.bin": T4, "t5.bin": T5, "t6.bin": T6}
        for name, blob in fixture_bytes.items():
            (fix / name).write_bytes(blob)
        data = pack(files)
        zip_path = self.root / "src" / "archive.zip"
        zip_path.write_bytes(data)
        binding = binding_for(files, fixtures)
        binding_path = self.root / "binding.json"
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        return zip_path, out, fix, binding_path, self.identity_from(data), data

    def args(self, zip_path, out, binding_path, fix, execute):
        argv = ["--zip", str(zip_path), "--output-dir", str(out)]
        if binding_path is not None:
            argv.extend(["--binding", str(binding_path)])
        if fix is not None:
            argv.extend(["--fixture-dir", str(fix)])
        if execute:
            argv.extend(["--execute", "--dedicated-vm"])
        return argv

    def test_frozen_identity_and_fixed_argv(self):
        self.assertEqual(mod.FROZEN.sha256, FROZEN_SHA)
        self.assertEqual(len(mod.FROZEN.sha256), 64)
        self.assertEqual(mod.FROZEN.nbytes, 42705)
        self.assertEqual(mod.FROZEN.regular_files, 18)
        self.assertEqual(mod.FROZEN.uncompressed_bytes, 95203)
        self.assertEqual([step.id for step in mod.STEP_TABLE], STEP_IDS)
        self.assertEqual(
            [step.argv for step in mod.STEP_TABLE],
            [
                ("python3", "-m", "unittest", "test_status_tool", "-v"),
                ("python3", "status_tool.py", "--file", "status_input.json"),
                ("python3", "status_tool.py"),
                ("python3", "status_tool.py"),
                ("python3", "status_tool.py"),
                ("python3", "status_tool.py"),
                ("python3", "-m", "unittest", "test_preflight", "-v"),
                ("python3", "preflight.py"),
            ],
        )
        self.assertTrue(all(step.argv[0] == "python3" for step in mod.STEP_TABLE))
        self.assertEqual(mod.STEP_TABLE[7].map_expected_exit, 0)
        self.assertEqual(mod.STEP_TABLE[7].historical_other_exit, 3)
        self.assertEqual(mod.STDIN_SIZES, {"T4": 2, "T5": 8, "T6": 19})
        source = TOOL_PATH.read_text(encoding="utf-8")
        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("extractall", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("OPENSSH", source)
        self.assertNotIn("ssh-ed25519", source)

    def test_synthetic_eight_steps_keep_s1_untested_and_preflight_conflict(self):
        self.assertEqual(len(T4), 2)
        self.assertEqual(len(T5), 8)
        self.assertEqual(len(T6), 19)
        files = core_files()
        zip_path, out, fix, binding_path, identity, before = self.prepare(files)
        os.chmod(zip_path, 0o444)
        mode = zip_path.stat().st_mode
        code, receipt, text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 0)
        self.assertEqual(receipt["technical_status"], "complete")
        self.assertTrue(receipt["executed"])
        self.assertEqual(receipt["scratch"], "removed")
        self.assertEqual(receipt["pycache_entries"], 0)
        self.assertTrue(receipt["archive"]["source_unchanged"])
        self.assertEqual(receipt["archive"]["identity"], "match")
        self.assertEqual([step["exit_code"] for step in receipt["steps"]], [0, 0, 0, 0, 2, 2, 0, 0])
        self.assertTrue(all(step["technical_status"] == "executed" for step in receipt["steps"]))
        t2, t3, t4 = receipt["steps"][1], receipt["steps"][2], receipt["steps"][3]
        self.assertEqual(t3["stdout_relation"], "match")
        self.assertEqual(t3["stdout_sha256"], t2["stdout_sha256"])
        self.assertNotEqual(t4["stdout_sha256"], t2["stdout_sha256"])
        self.assertEqual(t3["stdin_sha256"], sha256(STATUS_INPUT))
        self.assertEqual(receipt["steps"][3]["stdin_bytes"], 2)
        self.assertEqual(receipt["steps"][4]["stdin_bytes"], 8)
        self.assertEqual(receipt["steps"][5]["stdin_bytes"], 19)
        preflight = receipt["steps"][7]
        self.assertEqual(preflight["actual_vs_map"], "match")
        self.assertEqual(preflight["historical_other_exit"], 3)
        self.assertEqual(preflight["historical_conflict"], "UNRESOLVED")
        self.assertEqual(zip_path.read_bytes(), before)
        self.assertEqual(zip_path.stat().st_mode, mode)
        self.assertEqual((out / "receipt.json").read_text(encoding="ascii"), text)
        self.assertFalse(any(path.name.startswith("s1scratch-") for path in out.iterdir()))
        self.assertFalse(any(path.name == "__pycache__" for path in out.rglob("*")))
        notes = next(item for item in receipt["members"] if item["path"] == "notes.txt")
        self.assertEqual(notes["sha256"], sha256(files["notes.txt"]))
        self.assertNotIn(CANARY, text)

    def test_preflight_exit_3_stays_unresolved_conflict(self):
        files = core_files(preflight=PREFLIGHT_EXIT3)
        zip_path, out, fix, binding_path, identity, _before = self.prepare(files)
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 0)
        self.assertEqual(receipt["technical_status"], "complete")
        preflight = receipt["steps"][7]
        self.assertEqual(preflight["exit_code"], 3)
        self.assertEqual(preflight["map_expected_exit"], 0)
        self.assertEqual(preflight["actual_vs_map"], "mismatch")
        self.assertEqual(preflight["historical_other_exit"], 3)
        self.assertEqual(preflight["historical_conflict"], "UNRESOLVED")
        self.assertEqual(receipt["s1_judgment"], "NOT_TESTED")

    def test_inspect_does_not_execute_a_matching_archive(self):
        marker = self.root / "ran-marker"
        files = core_files(status=marker_program(str(marker)))
        zip_path, out, fix, binding_path, identity, before = self.prepare(files)
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=False), identity=identity
        )
        self.assertEqual(code, 0)
        self.assertEqual(receipt["mode"], "inspect")
        self.assertEqual(receipt["technical_status"], "inspect-only")
        self.assertFalse(receipt["executed"])
        self.assertEqual(receipt["scratch"], "not-created")
        self.assertTrue(all(step["technical_status"] == "not-run" for step in receipt["steps"]))
        self.assertEqual(receipt["steps"][7]["historical_conflict"], "UNRESOLVED")
        self.assertFalse(marker.exists())
        self.assertEqual(zip_path.read_bytes(), before)

    def test_cli_refuses_unknown_archive_without_running_it(self):
        marker = self.root / "ran-marker"
        files = core_files(status=marker_program(str(marker)))
        zip_path, out, fix, binding_path, _identity, before = self.prepare(files)
        proc = subprocess.run(
            [sys.executable, str(TOOL_PATH), *self.args(zip_path, out, binding_path, fix, execute=True)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1)
        self.assert_sanitized(proc.stdout, json.loads(proc.stdout))
        self.assertNotIn(CANARY, proc.stderr)
        self.assertNotIn("CANARYPATH", proc.stderr)
        receipt = json.loads(proc.stdout)
        self.assertEqual(receipt["archive"]["identity"], "mismatch")
        self.assertEqual(receipt["reason"], "identity-mismatch")
        self.assertFalse(receipt["executed"])
        self.assertEqual(receipt["required_identity"]["sha256"], FROZEN_SHA)
        self.assertEqual(receipt["required_identity"]["bytes"], 42705)
        self.assertFalse(marker.exists())
        self.assertEqual(zip_path.read_bytes(), before)

    def test_execute_requires_dedicated_vm_acknowledgement_before_reading(self):
        out = self.root / "out"
        out.mkdir()
        missing = self.root / "missing.zip"
        code, receipt, _text = self.run_main(
            ["--execute", "--zip", str(missing), "--output-dir", str(out), "--binding", "binding.json", "--fixture-dir", "fix"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "dedicated-vm-acknowledgement-required")
        self.assertFalse(receipt["executed"])
        self.assertFalse((out / "receipt.json").exists())

    def test_missing_binding_field_and_unknown_command_fail_closed(self):
        files = core_files()
        zip_path, out, fix, binding_path, identity, _before = self.prepare(files)
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        del binding["stdin_fixtures"]["T6"]
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "binding-invalid")
        self.assertFalse(receipt["executed"])

        binding = binding_for(files)
        binding["command"] = "echo hi"
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "binding-invalid")
        self.assertFalse(receipt["executed"])

        duplicate = (
            '{"schema_version":"s1-linux-eight-binding/v0",'
            '"schema_version":"s1-linux-eight-binding/v0"}'
        )
        binding_path.write_text(duplicate, encoding="utf-8")
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "binding-invalid")
        self.assertFalse((self.root / "ran-marker").exists())

        binding = binding_for(files)
        del binding["members"]["notes.txt"]
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "binding-incomplete")
        self.assertIn("unpinned:notes.txt", receipt["binding_problems"])
        self.assertFalse(receipt["executed"])

    def test_wrong_member_and_fixture_hashes_do_not_run(self):
        marker = self.root / "ran-marker"
        files = core_files(status=marker_program(str(marker)))
        zip_path, out, fix, binding_path, identity, before = self.prepare(files)
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        binding["members"]["status_tool.py"] = "0" * 64
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "member-sha-mismatch")
        self.assertEqual(receipt["binding_status"], "sha-mismatch")
        self.assertFalse(receipt["executed"])
        self.assertFalse(marker.exists())
        self.assertEqual(zip_path.read_bytes(), before)

        binding = binding_for(files)
        binding["stdin_fixtures"]["T4"]["sha256"] = "ab" * 32
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "fixture-sha-mismatch")
        self.assertFalse(marker.exists())

        (fix / "t4.bin").write_bytes(b"ABC")
        binding = binding_for(files)
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "fixture-length")
        self.assertFalse(marker.exists())

    def test_path_escape_duplicate_symlink_and_special_file(self):
        cases = {
            "path-escape": [("../CANARY-ESCAPE", b"nope")],
            "duplicate-path": [("dup.txt", b"one"), ("dup.txt", CANARY.encode())],
            "symlink": None,
            "special-file": None,
        }
        for reason, entries in cases.items():
            buffer = io.BytesIO()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(buffer, "w") as archive:
                    if reason == "symlink":
                        info = zipfile.ZipInfo("link")
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(info, b"target")
                    elif reason == "special-file":
                        info = zipfile.ZipInfo("pipe")
                        info.create_system = 3
                        info.external_attr = (stat.S_IFIFO | 0o644) << 16
                        archive.writestr(info, b"x")
                    else:
                        for name, blob in entries:
                            archive.writestr(name, blob)
            hold = self.root / "hold" / reason
            hold.mkdir(parents=True)
            zip_path = hold / "archive.zip"
            zip_path.write_bytes(buffer.getvalue())
            out = self.root / "outs" / reason
            out.mkdir(parents=True)
            code, receipt, text = self.run_main(["--zip", str(zip_path), "--output-dir", str(out)])
            self.assertEqual(code, 1, reason)
            self.assertEqual(receipt["reason"], "zip-unsafe", reason)
            self.assertIn(reason if reason != "symlink" else "symlink", receipt["archive"]["safety_reasons"])
            self.assertEqual(receipt["members"], [])
            self.assertFalse(receipt["executed"])
            self.assertNotIn("CANARY-ESCAPE", text)
            self.assertNotIn(CANARY, text)

    def test_nested_member_is_not_executed(self):
        marker = self.root / "ran-marker"
        files = core_files(extra={"nested/leaf.py": marker_program(str(marker)).encode()})
        data = pack(files)
        zip_path = self.root / "src"
        zip_path.mkdir()
        archive = zip_path / "archive.zip"
        archive.write_bytes(data)
        out = self.root / "out"
        out.mkdir()
        identity = self.identity_from(data)
        self.assertEqual(identity.regular_files, 9)
        binding = binding_for({name: blob for name, blob in files.items() if "/" not in name})
        binding_path = self.root / "binding.json"
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        fix = self.root / "fix"
        fix.mkdir()
        for name, blob in {"t4.bin": T4, "t5.bin": T5, "t6.bin": T6}.items():
            (fix / name).write_bytes(blob)
        code, receipt, text = self.run_main(
            self.args(archive, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "layout-not-flat")
        self.assertEqual(receipt["archive"]["layout"], "nested")
        self.assertFalse(receipt["executed"])
        self.assertFalse(marker.exists())
        self.assertNotIn(CANARY, text)

    def test_size_count_and_ratio_caps(self):
        fat = {"big.bin": b"Q" * (300 * 1024)}
        many = {f"f{index}.txt": b"a" for index in range(65)}
        zeros = {"zeros.bin": b"\x00" * (100 * 1024)}
        expected = (
            (fat, "member-too-large"),
            (many, "too-many-members"),
            (zeros, "compression-ratio"),
        )
        for index, (files, reason) in enumerate(expected):
            data = pack(files)
            hold = self.root / "caps" / str(index)
            hold.mkdir(parents=True)
            zip_path = hold / "archive.zip"
            zip_path.write_bytes(data)
            out = self.root / "cap-outs" / str(index)
            out.mkdir(parents=True)
            code, receipt, text = self.run_main(["--zip", str(zip_path), "--output-dir", str(out)])
            self.assertEqual(code, 1)
            self.assertEqual(receipt["reason"], "zip-unsafe")
            self.assertIn(reason, receipt["archive"]["safety_reasons"])
            self.assertNotIn("QQQQQQQQ", text)
            self.assertEqual(receipt["members"], [])

    def test_timeout_and_output_limit_stop_later_steps(self):
        marker = self.root / "ran-marker"
        sleepy = core_files(
            status=marker_program(str(marker)),
            tests=touch_source(marker, delay=30).encode(),
        )
        zip_path, out, fix, binding_path, identity, _before = self.prepare(sleepy)
        started = time.monotonic()
        code, receipt, _text = mod_perform(
            self, zip_path, out, binding_path, fix, identity, timeout=0.4, max_output=mod.MAX_STREAM_BYTES
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 5)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "timeout")
        self.assertEqual(receipt["technical_status"], "interrupted")
        self.assertEqual(receipt["steps"][0]["technical_status"], "timeout")
        self.assertEqual(receipt["steps"][1]["technical_status"], "not-run")
        self.assertFalse(marker.exists())
        self.assertEqual(receipt["scratch"], "removed")

        flood = """\
import os
import unittest

class Synthetic(unittest.TestCase):
    def test_flood(self):
        os.write(2, b"Y" * 8000)
"""
        files = core_files(status=marker_program(str(marker)), tests=flood.encode())
        zip_path, out, fix, binding_path, identity, _before = self.prepare(files)
        code, receipt, text = mod_perform(
            self, zip_path, out, binding_path, fix, identity, timeout=5, max_output=128
        )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "output-limit")
        self.assertEqual(receipt["steps"][0]["technical_status"], "output-limit")
        self.assertTrue(receipt["steps"][0]["stderr_truncated"])
        self.assertLessEqual(receipt["steps"][0]["stderr_bytes"], 128)
        self.assertEqual(receipt["steps"][1]["technical_status"], "not-run")
        self.assertFalse(marker.exists())
        self.assertNotIn("YYYYYYYY", text)

    def test_start_failure_and_rejected_cli_switches(self):
        files = core_files()
        zip_path, out, fix, binding_path, identity, _before = self.prepare(files)
        saved = mod.CHILD_PATH
        mod.CHILD_PATH = "/no/such/s1-bin"
        try:
            code, receipt, _text = mod_perform(
                self, zip_path, out, binding_path, fix, identity, timeout=5, max_output=1024
            )
        finally:
            mod.CHILD_PATH = saved
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "start-failed")
        self.assertEqual(receipt["steps"][0]["exit_code"], 127)
        self.assertEqual(receipt["steps"][1]["technical_status"], "not-run")
        self.assertEqual(receipt["s1_judgment"], "NOT_TESTED")

        proc = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--zip", str(zip_path), "--output-dir", str(out), "--timeout", "1"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn(CANARY, proc.stderr)
        proc = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--zip", str(zip_path), "--output-dir", str(out), "--argv", "bash"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)

    def test_census_conflict_output_overlap_and_symlinks(self):
        files = core_files()
        zip_path, out, fix, binding_path, identity, _before = self.prepare(files)
        bad = mod.ArchiveIdentity(
            identity.sha256, identity.nbytes, identity.regular_files + 1, identity.uncompressed_bytes
        )
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=bad
        )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "census-conflict")
        self.assertFalse(receipt["executed"])

        overlap = self.root / "src" / "nested-out"
        overlap.mkdir()
        code, receipt, _text = self.run_main(
            ["--zip", str(zip_path), "--output-dir", str(overlap)], identity=identity
        )
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "output-dir-overlaps-source")
        self.assertFalse((overlap / "receipt.json").exists())

        link_zip = self.root / "src" / "linked.zip"
        link_zip.symlink_to(zip_path)
        code, receipt, _text = self.run_main(["--zip", str(link_zip), "--output-dir", str(out)])
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "zip-is-symlink")

        linked_out = self.root / "linked-out"
        linked_out.symlink_to(out)
        code, receipt, _text = self.run_main(["--zip", str(zip_path), "--output-dir", str(linked_out)])
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "output-dir-unsafe")

        binding = binding_for(files)
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        target = self.root / "real-t4.bin"
        target.write_bytes(T4)
        fixture = fix / "t4.bin"
        fixture.unlink()
        fixture.symlink_to(target)
        code, receipt, _text = self.run_main(
            self.args(zip_path, out, binding_path, fix, execute=True), identity=identity
        )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "fixture-unreadable")
        self.assertFalse(receipt["executed"])


def mod_perform(test, zip_path, out, binding_path, fix, identity, timeout, max_output):
    code, receipt, text = mod.perform(
        str(zip_path),
        str(out),
        execute=True,
        dedicated_vm=True,
        binding_path=str(binding_path),
        fixture_dir=str(fix),
        identity=identity,
        timeout=timeout,
        max_output=max_output,
    )
    test.assert_sanitized(text, receipt)
    file_text = (out / "receipt.json").read_text(encoding="ascii")
    test.assertEqual(file_text, text)
    return code, receipt, text


if __name__ == "__main__":
    unittest.main()
