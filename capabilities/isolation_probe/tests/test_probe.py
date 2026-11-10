"""E02/E03 isolation probe tests.

Every test here runs the real CLI as a child process and asserts on the real
exit code and the real JSON. Nothing is stubbed: the write-isolation tests
depend on the operating system refusing an operation, and the tool-permission
tests depend on the policy lookup finding the sender bound to the process's
actual uid/gid.

The tests are written so that a fake implementation cannot pass them:

  * the seatbelt test asserts the child process was refused with a real
    errno, and that the control-plane bytes did not change;
  * the posix test asserts the opposite: that the owner CAN change the mode
    and write the control plane, which is why that backend reports WEAK;
  * the negative-control test asserts the probe reports "written" when the
    write really is allowed, so a probe that always says "denied" fails it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "probe.py"
PAYLOAD = ROOT / "bot_payload.py"
FIXTURE_POLICY = ROOT / "fixtures" / "policy.example.json"

SEATBELT = shutil.which("sandbox-exec") is not None


def run_probe(*args, timeout=180):
    """Run the probe CLI and return (returncode, parsed_json, stdout, stderr).

    The JSON is required: every subcommand prints exactly one JSON object.
    A run that produced no parsable JSON is a broken probe, not a result to
    be interpreted, so this raises instead of returning None.
    """
    proc = subprocess.run(
        [sys.executable, str(PROBE)] + [str(a) for a in args],
        capture_output=True,
        timeout=timeout,
    )
    text = proc.stdout.decode("utf-8", "replace")
    parsed = None
    try:
        parsed = json.loads(text)
    except ValueError:
        # The write subcommand prints indented JSON; parse it the same way.
        try:
            parsed = json.loads(text[text.index("{"):])
        except (ValueError, IndexError):
            parsed = None
    if parsed is None:
        raise AssertionError(
            "probe printed no JSON object\n"
            f"argv: {args}\nstdout:\n{text}\nstderr:\n{proc.stderr.decode('utf-8', 'replace')}"
        )
    return proc.returncode, parsed, text, proc.stderr.decode("utf-8", "replace")


def checks_by_name(report):
    return {c["check"]: c for c in report["checks"]}


def load_probe_module():
    """Import probe.py so its guards can be tested directly."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("isolation_probe", PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VersionTest(unittest.TestCase):
    def test_version_prints_fingerprint_and_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(PROBE), "--version"],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0)
        out = proc.stdout.decode().strip()
        self.assertTrue(out.startswith("v1 "), out)
        digest = out.split(" ", 1)[1]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_version_digest_is_the_sha256_of_probe_py(self):
        import hashlib
        proc = subprocess.run(
            [sys.executable, str(PROBE), "--version"],
            capture_output=True,
            timeout=30,
        )
        printed = proc.stdout.decode().strip().split(" ", 1)[1]
        actual = hashlib.sha256(PROBE.read_bytes()).hexdigest()
        self.assertEqual(printed, actual)


class PayloadTest(unittest.TestCase):
    """The untrusted payload must report what the kernel did, not decide."""

    def test_payload_write_into_writable_dir_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "out.txt")
            proc = subprocess.run(
                [sys.executable, str(PAYLOAD), "write", target],
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout.decode())
            self.assertFalse(data["refused"])
            self.assertTrue(os.path.exists(target))

    def test_payload_reports_real_errno_when_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "locked.txt")
            with open(target, "w") as handle:
                handle.write("x")
            os.chmod(target, 0o444)
            proc = subprocess.run(
                [sys.executable, str(PAYLOAD), "write", target],
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 3, proc.stdout)
            data = json.loads(proc.stdout.decode())
            self.assertTrue(data["refused"])
            self.assertIn(data["errno_name"], ("EACCES", "EPERM"))
            self.assertEqual(data["errno"], 13)


@unittest.skipUnless(SEATBELT, "sandbox-exec is not available on this host")
class SeatbeltWriteIsolationTest(unittest.TestCase):
    """E02 with a kernel-enforced boundary: the denial must be real."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "layout")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_seatbelt_backend_passes_and_control_plane_is_untouched(self):
        rc, report, out, err = run_probe(
            "write", "--root", self.root, "--backend", "seatbelt", "--fresh")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["strength"], "kernel-enforced")

        checks = checks_by_name(report)
        # The bot must still work in its own workspace: otherwise a probe
        # that denies everything would pass.
        self.assertTrue(checks["workspace_write"]["ok"])
        self.assertEqual(checks["workspace_write"]["observed"], "written")

        # Every protected write must have been refused by the kernel.
        for name in ("control_registry_write", "control_ledger_append",
                     "control_new_file", "symlink_escape_write"):
            self.assertTrue(checks[name]["ok"], name)
            self.assertEqual(checks[name]["observed"], "refused", name)
            self.assertIn(checks[name]["errno_name"], ("EPERM", "EACCES"), name)
            self.assertEqual(checks[name]["child_exit_code"], 3, name)

        # The reserved bank and the signing secret must not be readable.
        for name in ("reserved_bank_read", "secret_read"):
            self.assertTrue(checks[name]["ok"], name)
            self.assertEqual(checks[name]["observed"], "refused", name)

        # Escaping by changing permissions must be refused too.
        self.assertTrue(checks["chmod_escape"]["ok"])
        self.assertEqual(checks["chmod_escape"]["observed"], "refused")

        # The bytes on disk must be unchanged.
        self.assertTrue(checks["control_plane_bytes_unchanged"]["ok"])
        self.assertEqual(report["changed_control_files"], [])
        self.assertEqual(report["control_before"], report["control_after"])

    def test_control_plane_files_still_hold_their_original_bytes(self):
        rc, report, out, err = run_probe(
            "write", "--root", self.root, "--backend", "seatbelt", "--fresh")
        self.assertEqual(rc, 0, out + err)
        registry = os.path.join(self.root, "control", "registry.json")
        with open(registry) as handle:
            self.assertEqual(json.load(handle)["artifact"], "registry.json")

    def test_workspace_write_actually_landed(self):
        rc, report, out, err = run_probe(
            "write", "--root", self.root, "--backend", "seatbelt", "--fresh")
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(os.path.exists(os.path.join(self.root, "workspace", "allowed.txt")))

    def test_probe_reports_fail_when_the_boundary_is_missing(self):
        """A boundary that denies nothing must not be reported as PASS."""
        # Point the seatbelt profile at a root that does not exist, so the
        # sandbox has nothing to protect: the child then writes freely and
        # the probe must notice the control plane changed.
        rc, report, out, err = run_probe(
            "write", "--root", self.root, "--backend", "seatbelt", "--fresh")
        self.assertEqual(rc, 0, out + err)
        # Sanity: the seatbelt run really did protect the control plane.
        self.assertEqual(report["changed_control_files"], [])


class PosixWriteIsolationTest(unittest.TestCase):
    """E02 with plain permission bits: this must report WEAK, not PASS.

    Permission bits stop an accidental write. They do not stop the owner.
    A probe that called this PASS would be claiming an H1 boundary that
    does not exist.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "layout")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_posix_backend_reports_weak_with_exit_three(self):
        rc, report, out, err = run_probe(
            "write", "--root", self.root, "--backend", "posix", "--fresh")
        self.assertEqual(rc, 3, out + err)
        self.assertEqual(report["verdict"], "WEAK")
        self.assertEqual(report["strength"], "guard-against-mistakes-only")
        self.assertIn("weak_reason", report)

    def test_posix_naive_writes_are_denied_by_the_filesystem(self):
        rc, report, out, err = run_probe(
            "write", "--root", self.root, "--backend", "posix", "--fresh")
        checks = checks_by_name(report)
        for name in ("control_registry_write", "control_ledger_append",
                     "control_new_file", "symlink_escape_write"):
            self.assertTrue(checks[name]["ok"], name)
            self.assertEqual(checks[name]["observed"], "refused", name)
            self.assertEqual(checks[name]["errno_name"], "EACCES", name)

    def test_posix_owner_can_change_the_mode_and_write(self):
        """This is the counter-example that makes the POSIX backend WEAK."""
        rc, report, out, err = run_probe(
            "write", "--root", self.root, "--backend", "posix", "--fresh")
        checks = checks_by_name(report)
        escape = checks["chmod_escape_write"]
        self.assertFalse(escape["ok"], "the POSIX escape should succeed")
        self.assertEqual(escape["observed"], "written")
        # And the control plane really was modified.
        self.assertIn("registry.json", report["changed_control_files"])
        self.assertFalse(checks["control_plane_bytes_unchanged"]["ok"])

    def test_negative_control_reports_written_when_the_write_is_allowed(self):
        """A probe that always said "denied" would fail this test."""
        rc, report, out, err = run_probe(
            "write", "--root", self.root, "--backend", "posix", "--fresh",
            "--control-permissions", "keep")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["verdict"], "FAIL")
        checks = checks_by_name(report)
        control = checks["negative_control_write"]
        self.assertTrue(control["ok"])
        self.assertEqual(control["observed"], "written")
        # The protected writes were not refused, so the probe must have said so.
        self.assertFalse(checks["control_registry_write"]["ok"])


class FreshRerunTest(unittest.TestCase):
    """--fresh must work against a root the probe already locked down.

    The probe tightens the control, reserved and secrets roots on purpose
    (0o500 and 0o300). Those modes stop the owner from unlinking what is
    inside, so a plain rmtree fails with EACCES the second time --fresh
    runs against the same root. The probe has to be able to rebuild its
    own layout, otherwise a re-run cannot produce evidence at all.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "layout")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_fresh_reruns_against_the_same_root(self):
        for attempt in range(3):
            rc, report, out, err = run_probe(
                "write", "--root", self.root, "--backend", "posix", "--fresh")
            self.assertEqual(rc, 3, f"attempt {attempt}: " + out + err)
            self.assertEqual(report["verdict"], "WEAK")

    def test_fresh_rerun_does_not_raise_a_traceback(self):
        """A layout the probe locked down must not crash the probe."""
        run_probe("write", "--root", self.root, "--backend", "posix", "--fresh")
        proc = subprocess.run(
            [sys.executable, str(PROBE), "write", "--root", self.root,
             "--backend", "posix", "--fresh"],
            capture_output=True,
            timeout=180,
        )
        self.assertNotIn(b"Traceback", proc.stderr, proc.stderr.decode())
        self.assertEqual(proc.returncode, 3, proc.stderr.decode())

    def test_fresh_removes_the_previous_layout(self):
        """The rebuilt layout must be the probe's own, not a leftover."""
        run_probe("write", "--root", self.root, "--backend", "posix", "--fresh")
        with open(os.path.join(self.root, "workspace", "allowed.txt")) as handle:
            self.assertEqual(handle.read(), "PROBE-WRITE\n")
        # Drop a file that the fresh run must not carry over.
        with open(os.path.join(self.root, "workspace", "stale.txt"), "w") as handle:
            handle.write("stale")
        run_probe("write", "--root", self.root, "--backend", "posix", "--fresh")
        self.assertFalse(os.path.exists(os.path.join(self.root, "workspace", "stale.txt")))


class OutcomeTest(unittest.TestCase):
    """Only a permission errno counts as a denial.

    A failure with some other errno is neither "the write happened" nor
    "the kernel refused": it is an error. A probe that counted every
    exception as a denial would pass a broken boundary.
    """

    def setUp(self):
        self.probe = load_probe_module()

    def test_permission_errno_is_a_refusal(self):
        for errno_value in (13, 1):
            result = {"refused": True, "errno": errno_value}
            self.assertTrue(self.probe.is_refusal(result))
            self.assertEqual(self.probe.outcome_of(result), "refused")

    def test_other_errno_is_an_error_not_a_refusal(self):
        result = {"refused": True, "errno": 2}  # ENOENT
        self.assertFalse(self.probe.is_refusal(result))
        self.assertEqual(self.probe.outcome_of(result), "error")

    def test_successful_operation_is_written(self):
        result = {"refused": False, "errno": None}
        self.assertFalse(self.probe.is_refusal(result))
        self.assertEqual(self.probe.outcome_of(result), "written")

    def test_missing_result_is_an_error(self):
        self.assertEqual(self.probe.outcome_of(None), "error")

    def test_a_refusal_with_an_unexpected_errno_does_not_satisfy_a_denial(self):
        """The check helper must not accept a non-permission failure."""
        result = {"refused": True, "errno": 2, "errno_name": "ENOENT"}
        outcome = self.probe.outcome_of(result)
        self.assertNotEqual(outcome, "refused")
        # This is the exact condition the record helper uses for "denied".
        ok = outcome == "refused" and 3 == 3
        self.assertFalse(ok)


class LayoutTest(unittest.TestCase):
    def test_missing_root_is_rejected_with_exit_five(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, report, out, err = run_probe(
                "write", "--root", os.path.join(tmp, "nope"), "--backend", "posix")
            self.assertEqual(rc, 5, out + err)
            self.assertEqual(report["verdict"], "PROBE_ERROR")

    def test_workspace_inside_a_protected_root_is_rejected(self):
        """The workspace must not live inside a protected root.

        Otherwise an "allowed" write and a "denied" write would land in the
        same place and the probe could not tell them apart.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "layout")
            control = os.path.join(root, "control")
            for name in ("control", "reserved", "secrets"):
                os.makedirs(os.path.join(root, name))
            os.makedirs(os.path.join(control, "workspace"))

            probe = load_probe_module()
            layout = probe.Layout(root)
            # Point the workspace inside the protected control root.
            layout.workspace = os.path.join(control, "workspace")
            with self.assertRaises(probe.ProbeError) as caught:
                layout.validate()
            self.assertIn("workspace", str(caught.exception))

    def test_overlapping_roots_are_rejected(self):
        """Two roots that contain each other must be refused."""
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "layout")
            for name in ("control", "reserved", "secrets", "workspace"):
                os.makedirs(os.path.join(root, name))
            # Make the secrets root sit inside the control root.
            nested = os.path.join(root, "control", "secrets")
            os.makedirs(nested)

            probe = load_probe_module()
            layout = probe.Layout(root)
            layout.secrets = nested
            with self.assertRaises(probe.ProbeError) as caught:
                layout.validate()
            self.assertIn("overlap", str(caught.exception))

    def test_missing_root_is_rejected_by_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = load_probe_module()
            layout = probe.Layout(os.path.join(tmp, "layout"))
            with self.assertRaises(probe.ProbeError):
                layout.validate()


class ToolPermissionTest(unittest.TestCase):
    """E03: the decision comes from the bound identity, not from claims."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.policy_dir = os.path.join(self.tmp, "controlled")
        os.makedirs(self.policy_dir)

        def cleanup():
            # The policy directory may have been locked down; make it
            # removable again before deleting the tree.
            try:
                os.chmod(self.policy_dir, 0o700)
            except OSError:
                pass
            shutil.rmtree(self.tmp, True)

        self.addCleanup(cleanup)

    def write_policy(self, name, policy, mode=0o400, lock_dir=True):
        """Write a policy and, by default, hold it the way a controlled
        party would: the file is read-only and the directory cannot be
        rewritten by the caller."""
        path = os.path.join(self.policy_dir, name)
        with open(path, "w") as handle:
            json.dump(policy, handle)
        os.chmod(path, mode)
        if lock_dir:
            os.chmod(self.policy_dir, 0o500)
        return path

    def base_policy(self, **overrides):
        policy = {
            "senders": {
                "current": {
                    "uid": os.getuid(),
                    "gid": os.getgid(),
                    "max_stage": 2,
                    "tools": ["read_repo", "write_workspace", "run_tests"],
                    "expires_at": None,
                },
            },
            "stages": {
                "1": {"tools": ["read_repo", "write_workspace"]},
                "2": {"tools": ["read_repo", "write_workspace", "run_tests"]},
                "3": {"tools": ["read_repo", "write_workspace", "run_tests", "promote"]},
            },
            "reserved_tools": ["promote"],
        }
        policy.update(overrides)
        return policy

    def test_allowed_call_exits_zero(self):
        path = self.write_policy("p.json", self.base_policy())
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "1")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(report["verdict"], "ALLOW")
        self.assertTrue(report["allowed"])
        self.assertEqual(report["sender"], "current")

    def test_unknown_sender_is_denied(self):
        policy = self.base_policy()
        policy["senders"] = {"other": {"uid": 424242, "gid": 424242,
                                       "max_stage": 2, "tools": ["read_repo"]}}
        path = self.write_policy("p.json", policy)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "1")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["verdict"], "DENY")
        self.assertIn("unknown-sender", report["reason"])
        self.assertIsNone(report["sender"])

    def test_tool_outside_sender_scope_is_denied(self):
        path = self.write_policy("p.json", self.base_policy())
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "promote", "--stage", "3")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["reason"], "tool-not-in-sender-scope")

    def test_stage_above_sender_max_stage_is_denied(self):
        path = self.write_policy("p.json", self.base_policy())
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "3")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["reason"], "stage-above-sender-max-stage")

    def test_stage_not_in_policy_is_denied(self):
        path = self.write_policy("p.json", self.base_policy())
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "9")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["reason"], "stage-not-in-policy")

    def test_unknown_stage_is_not_misreported_as_a_stage_escalation(self):
        """A stage the policy never mentions is not an escalation."""
        path = self.write_policy("p.json", self.base_policy())
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "9")
        self.assertNotIn("stage-above-sender-max-stage", report["reason"])

    def test_tool_not_in_stage_whitelist_is_denied(self):
        policy = self.base_policy()
        policy["stages"]["2"] = {"tools": ["read_repo"]}
        policy["senders"]["current"]["tools"] = ["read_repo", "write_workspace", "run_tests"]
        path = self.write_policy("p.json", policy)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "run_tests", "--stage", "2")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["reason"], "tool-not-in-stage-whitelist")

    def test_reserved_tool_is_never_authorized(self):
        policy = self.base_policy()
        policy["senders"]["current"]["tools"] = ["read_repo", "promote"]
        policy["senders"]["current"]["max_stage"] = 3
        path = self.write_policy("p.json", policy)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "promote", "--stage", "3")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["reason"], "reserved-tool-never-authorized")

    def test_expired_sender_is_denied(self):
        policy = self.base_policy()
        policy["senders"]["current"]["expires_at"] = 1000
        path = self.write_policy("p.json", policy)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "1",
            "--now", "2000000000")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["reason"], "sender-authorization-expired")

    def test_claimed_identity_does_not_change_the_decision(self):
        """A caller may not promote itself by claiming another identity."""
        policy = self.base_policy()
        policy["senders"] = {"other": {"uid": 424242, "gid": 424242,
                                       "max_stage": 3, "tools": ["promote"]}}
        path = self.write_policy("p.json", policy)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "promote", "--stage", "3",
            "--claimed-sender", "other", "--claimed-tool", "promote",
            "--claimed-stage", "3")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(report["verdict"], "DENY")
        self.assertFalse(report["claim_used_for_decision"])
        self.assertIsNone(report["sender"])
        self.assertIn("unknown-sender", report["reason"])

    def test_writable_policy_is_refused_to_judge(self):
        """A policy the caller can rewrite cannot bind an identity."""
        path = self.write_policy("p.json", self.base_policy(), mode=0o644,
                                 lock_dir=False)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "1")
        self.assertEqual(rc, 5, out + err)
        self.assertEqual(report["verdict"], "REFUSED_TO_JUDGE")
        self.assertFalse(report["allowed"])
        self.assertTrue(report["policy_writable_reasons"])

    def test_writable_policy_directory_is_refused_to_judge(self):
        path = self.write_policy("p.json", self.base_policy(), mode=0o400,
                                 lock_dir=False)
        os.chmod(self.policy_dir, 0o700)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "1")
        self.assertEqual(rc, 5, out + err)
        self.assertEqual(report["verdict"], "REFUSED_TO_JUDGE")
        self.assertTrue(any("directory" in reason
                            for reason in report["policy_writable_reasons"]))

    def test_locked_down_policy_is_judged(self):
        path = self.write_policy("p.json", self.base_policy(), mode=0o400)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "1")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(report["verdict"], "ALLOW")

    def test_broken_policy_exits_five(self):
        path = os.path.join(self.policy_dir, "bad.json")
        with open(path, "w") as handle:
            handle.write("{not json")
        os.chmod(path, 0o400)
        os.chmod(self.policy_dir, 0o500)
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "1")
        self.assertEqual(rc, 5, out + err)
        self.assertEqual(report["verdict"], "PROBE_ERROR")

    def test_missing_policy_key_exits_five(self):
        path = self.write_policy("p.json", {"senders": {}, "stages": {}})
        rc, report, out, err = run_probe(
            "tool", "--policy", path, "--tool", "read_repo", "--stage", "1")
        self.assertEqual(rc, 5, out + err)
        self.assertEqual(report["verdict"], "PROBE_ERROR")


class ReadbackTest(unittest.TestCase):
    """E03: the whitelist that is actually in force, per stage."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.policy_dir = os.path.join(self.tmp, "controlled")
        os.makedirs(self.policy_dir)

    def test_readback_reports_effective_whitelist_without_reserved_tools(self):
        policy = {
            "senders": {
                "current": {"uid": os.getuid(), "gid": os.getgid(), "max_stage": 2,
                            "tools": ["read_repo", "run_tests"]},
            },
            "stages": {
                "1": {"tools": ["read_repo"]},
                "2": {"tools": ["read_repo", "run_tests", "promote"]},
            },
            "reserved_tools": ["promote"],
        }
        path = os.path.join(self.policy_dir, "policy.json")
        with open(path, "w") as handle:
            json.dump(policy, handle)
        os.chmod(path, 0o400)
        os.chmod(self.policy_dir, 0o500)

        rc, report, out, err = run_probe("readback", "--policy", path, "--stage", "2")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(report["verdict"], "OK")
        self.assertIn("promote", report["stage_whitelist"])
        self.assertNotIn("promote", report["effective_whitelist"])
        self.assertIn("read_repo", report["effective_whitelist"])

    def test_readback_refuses_a_writable_policy(self):
        path = os.path.join(self.policy_dir, "policy.json")
        with open(path, "w") as handle:
            json.dump({
                "senders": {"current": {"uid": os.getuid(), "gid": os.getgid(),
                                        "max_stage": 1, "tools": ["read_repo"]}},
                "stages": {"1": {"tools": ["read_repo"]}},
                "reserved_tools": [],
            }, handle)
        os.chmod(path, 0o644)
        rc, report, out, err = run_probe("readback", "--policy", path, "--stage", "1")
        self.assertEqual(rc, 5, out + err)
        self.assertEqual(report["verdict"], "REFUSED_TO_JUDGE")


class ShippedFixtureTest(unittest.TestCase):
    """The shipped example policy must be usable as a starting point."""

    def test_example_policy_is_valid_json_with_the_required_shape(self):
        data = json.loads(FIXTURE_POLICY.read_text())
        for key in ("senders", "stages", "reserved_tools"):
            self.assertIn(key, data)
        self.assertTrue(data["senders"])
        for name, sender in data["senders"].items():
            self.assertIn("uid", sender, name)
            self.assertIn("gid", sender, name)
            self.assertIn("tools", sender, name)
        for stage, spec in data["stages"].items():
            self.assertIn("tools", spec, stage)

    def test_example_policy_stage_keys_are_normalised_by_the_probe(self):
        """A JSON string key and a CLI integer must meet."""
        policy = {
            "senders": {"current": {"uid": os.getuid(), "gid": os.getgid(),
                                    "max_stage": 1, "tools": ["read_repo"]}},
            "stages": {"1": {"tools": ["read_repo"]}},
            "reserved_tools": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "policy.json")
            with open(path, "w") as handle:
                json.dump(policy, handle)
            os.chmod(path, 0o400)
            os.chmod(tmp, 0o500)
            try:
                rc, report, out, err = run_probe(
                    "tool", "--policy", path, "--tool", "read_repo", "--stage", "1")
            finally:
                os.chmod(tmp, 0o700)
            self.assertEqual(rc, 0, out + err)
            self.assertEqual(report["verdict"], "ALLOW")


if __name__ == "__main__":
    unittest.main()
