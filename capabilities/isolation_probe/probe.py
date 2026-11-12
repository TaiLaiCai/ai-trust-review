#!/usr/bin/env python3
"""Real Bot write-isolation and tool-permission probe (E02/E03).

The point of this capability is that a denial must come from the operating
system, not from this program comparing path strings. Every verdict below is
produced by running an untrusted child process and reading what the kernel
actually did to it.

Two subcommands:

  write    E02 - build a write boundary, then let an untrusted child process
           try to write outside its workspace. A denial is real only if the
           child process was refused by the kernel and the protected bytes
           are unchanged afterwards.

  tool     E03 - decide whether a tool call is allowed. The decision is bound
           to a sender identity that the policy file's owner controls, not to
           anything the caller claims about itself. The process exit code is
           the gate: 0 allows, 1 denies.

Exit codes (all subcommands):
  0  the probe ran and the observed behaviour matched the requirement
  1  the probe ran and the requirement was NOT met (a real, visible failure)
  2  usage error
  3  the boundary is weaker than required (writes were refused, but an escape
     was still possible)
  5  the probe could not run (bad layout, missing backend, bad policy)
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time

VERSION = "v1"

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(HERE, "bot_payload.py")

# Erno values that mean "the operating system refused this operation".
REFUSAL_ERRNOS = {13, 1, 30, 38}


class ProbeError(Exception):
    """The probe could not run. Maps to exit 5."""


def tool_fingerprint():
    """Version plus the sha256 of this file, so an operator can see the build."""
    with open(__file__, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return f"{VERSION} {digest}"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_tree(path):
    """Remove a tree the probe itself locked down.

    The probe deliberately sets restrictive modes on the control, reserved
    and secrets roots (0o500 and 0o300). Those modes stop the owner from
    listing or unlinking what is inside, so a plain rmtree fails with
    EACCES on the second --fresh run against the same root. Restore owner
    access first, then remove.

    Symlinks are never chmod-ed: rmtree unlinks the link itself, and
    chmod-ing it would touch whatever it points at. A root that is itself a
    symlink is refused outright: os.chmod on it would follow the link and
    loosen the permissions of whatever tree it points at, before any check
    could run.
    """
    if not os.path.lexists(path):
        return
    if os.path.islink(path):
        raise ProbeError(f"root must not be a symlink: {path}")
    os.chmod(path, 0o700)
    for root, dirs, files in os.walk(path):
        for name in dirs:
            target = os.path.join(root, name)
            if not os.path.islink(target):
                os.chmod(target, 0o700, follow_symlinks=False)
        for name in files:
            target = os.path.join(root, name)
            if not os.path.islink(target):
                os.chmod(target, 0o600, follow_symlinks=False)
    shutil.rmtree(path)


def is_within(child, parent):
    """True when `child` is `parent` or lives under it (realpath based)."""
    child_real = os.path.realpath(child)
    parent_real = os.path.realpath(parent)
    if child_real == parent_real:
        return True
    return child_real.startswith(parent_real.rstrip("/") + "/")


class Layout:
    """The four roots the probe works with.

    control   - registry / policy / ledger / snapshot: the controlled plane.
    reserved  - the reserved question bank.
    secrets   - signing secrets. Must never be readable by the bot.
    workspace - the only place the bot may write.
    """

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.control = os.path.join(self.root, "control")
        self.reserved = os.path.join(self.root, "reserved")
        self.secrets = os.path.join(self.root, "secrets")
        self.workspace = os.path.join(self.root, "workspace")

    @property
    def protected(self):
        return [self.control, self.reserved, self.secrets]

    def validate(self):
        """Every root must exist, be a real directory, and stay disjoint."""
        for path in [self.control, self.reserved, self.secrets, self.workspace]:
            if not os.path.isdir(path):
                raise ProbeError(f"missing root: {path}")
            if os.path.islink(path):
                raise ProbeError(f"root must not be a symlink: {path}")
        names = ["control", "reserved", "secrets", "workspace"]
        for i, first in enumerate(names):
            for second in names[i + 1:]:
                a = getattr(self, first)
                b = getattr(self, second)
                if is_within(a, b) or is_within(b, a):
                    raise ProbeError(f"roots overlap: {first} and {second}")
        # The workspace must not live inside any protected root: that would
        # make "allowed writes" indistinguishable from "denied writes".
        for path in self.protected:
            if is_within(self.workspace, path):
                raise ProbeError("workspace must not live inside a protected root")
        return self

    def build(self, tighten=True):
        """Create the layout with controlled-plane contents and permissions.

        `tighten=True` makes the control plane read-only, which is what the
        probe normally runs against. `tighten=False` leaves it writable; the
        negative control uses that to show the probe reports "written" when
        the write really is allowed.
        """
        os.makedirs(self.control, mode=0o700, exist_ok=True)
        os.makedirs(self.reserved, mode=0o700, exist_ok=True)
        os.makedirs(self.secrets, mode=0o700, exist_ok=True)
        os.makedirs(self.workspace, mode=0o700, exist_ok=True)

        # Control plane: readable, but not writable by the bot.
        for name in ("registry.json", "policy.json", "ledger.jsonl", "snapshot.json"):
            path = os.path.join(self.control, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"artifact": name, "owner": "controlled"}, sort_keys=True))
            os.chmod(path, 0o444 if tighten else 0o644)
        os.chmod(self.control, 0o500 if tighten else 0o700)

        # Reserved question bank: not readable, not writable.
        bank = os.path.join(self.reserved, "questions.json")
        with open(bank, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(["reserved"], ensure_ascii=False))
        os.chmod(bank, 0o000)
        os.chmod(self.reserved, 0o300)

        # Signing secret: not readable by the bot.
        secret = os.path.join(self.secrets, "signing.key")
        with open(secret, "w", encoding="utf-8") as handle:
            handle.write("SIGNING-SECRET-BYTES\n")
        os.chmod(secret, 0o000)
        os.chmod(self.secrets, 0o300)

        os.chmod(self.workspace, 0o700)
        return self

    def control_bytes(self):
        """sha256 of every control-plane file, for before/after comparison."""
        out = {}
        for name in sorted(os.listdir(self.control)):
            path = os.path.join(self.control, name)
            if os.path.isfile(path):
                out[name] = sha256_file(path)
        return out


def seatbelt_available():
    return shutil.which("sandbox-exec") is not None


def write_seatbelt_profile(layout, path):
    """Build a Seatbelt profile that denies the protected roots.

    The deny is expressed on the resolved paths, so a symlink inside the
    workspace that points at the control plane is still refused: the kernel
    resolves the path before applying the rule.
    """
    lines = ["(version 1)", "(allow default)"]
    for protected in layout.protected:
        resolved = os.path.realpath(protected)
        lines.append(f'(deny file-write* (subpath "{resolved}"))')
        lines.append(f'(deny file-read* (subpath "{resolved}"))')
        lines.append(f'(deny file-read-metadata (subpath "{resolved}"))')
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def run_payload(argv, sandbox_profile=None, cwd=None, env=None):
    """Run the untrusted payload as a real child process.

    Returns (returncode, parsed_json_or_None, raw_stdout, raw_stderr).
    """
    command = [sys.executable, PAYLOAD] + list(argv)
    if sandbox_profile:
        command = ["sandbox-exec", "-f", sandbox_profile] + command
    proc = subprocess.run(
        command,
        capture_output=True,
        timeout=60,
        cwd=cwd,
        env=env,
    )
    raw_out = proc.stdout.decode("utf-8", "replace")
    raw_err = proc.stderr.decode("utf-8", "replace")
    parsed = None
    for line in raw_out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except ValueError:
                parsed = None
    return proc.returncode, parsed, raw_out, raw_err


def is_refusal(result):
    """A refusal is the kernel refusing, not a script deciding.

    Only a permission-style errno counts. A failure with some other errno
    (a missing path, a broken filesystem) is not a denial and must not be
    counted as one.
    """
    if not result:
        return False
    if not result.get("refused"):
        return False
    return result.get("errno") in REFUSAL_ERRNOS


def outcome_of(result):
    """Classify what the child actually experienced.

    "written"  - the operation went through
    "refused"  - the kernel refused it with a permission errno
    "error"    - it failed for some other reason; that is not a denial
    """
    if result is None:
        return "error"
    if not result.get("refused"):
        return "written"
    if result.get("errno") in REFUSAL_ERRNOS:
        return "refused"
    return "error"


def probe_write(args):
    """E02. Build a boundary, then really try to escape it."""
    backend = args.backend
    if backend == "seatbelt" and not seatbelt_available():
        raise ProbeError("sandbox-exec is not available on this host")

    root = args.root
    # A symlink root must be refused before anything is chmod-ed or walked:
    # os.chmod follows links, so --fresh would first loosen the permissions
    # of whatever the link points at.
    if os.path.islink(root):
        raise ProbeError(f"root must not be a symlink: {root}")
    layout = Layout(root)
    tighten = args.control_permissions == "tighten"
    if args.fresh:
        if os.path.exists(root):
            remove_tree(root)
        layout.build(tighten=tighten)
    else:
        layout.validate()

    before = layout.control_bytes()
    profile_path = None
    if backend == "seatbelt":
        profile_path = write_seatbelt_profile(layout, os.path.join(root, "seatbelt.sb"))

    checks = []

    def record(name, expectation, result, returncode, note=""):
        outcome = outcome_of(result)
        if expectation == "allowed":
            ok = outcome == "written" and returncode == 0
        else:
            ok = outcome == "refused" and returncode == 3
        checks.append({
            "check": name,
            "expected": expectation,
            "observed": outcome,
            "errno": (result or {}).get("errno"),
            "errno_name": (result or {}).get("errno_name"),
            "child_exit_code": returncode,
            "ok": ok,
            "note": note,
        })
        return ok

    # 1. The workspace write must succeed. Without this, "everything refused"
    #    would look like a working boundary.
    workspace_target = os.path.join(layout.workspace, "allowed.txt")
    rc, result, out, err = run_payload(
        ["write", workspace_target],
        sandbox_profile=profile_path,
    )
    workspace_outcome = outcome_of(result)
    checks.append({
        "check": "workspace_write",
        "expected": "allowed",
        "observed": workspace_outcome,
        "errno": (result or {}).get("errno"),
        "errno_name": (result or {}).get("errno_name"),
        "child_exit_code": rc,
        "ok": workspace_outcome == "written" and rc == 0,
        "note": "the bot must still be able to work in its own workspace",
    })

    # 2. Control plane writes must be refused by the kernel.
    for name, target, action in (
        ("control_registry_write", os.path.join(layout.control, "registry.json"), "write"),
        ("control_ledger_append", os.path.join(layout.control, "ledger.jsonl"), "append"),
        ("control_new_file", os.path.join(layout.control, "injected.json"), "write"),
    ):
        rc, result, out, err = run_payload([action, target], sandbox_profile=profile_path)
        record(name, "denied", result, rc)

    # 3. The reserved bank and the signing secret must not be readable.
    for name, target in (
        ("reserved_bank_read", os.path.join(layout.reserved, "questions.json")),
        ("secret_read", os.path.join(layout.secrets, "signing.key")),
    ):
        rc, result, out, err = run_payload(["read", target], sandbox_profile=profile_path)
        record(name, "denied", result, rc)

    # 4. Symlink escape: a link inside the writable workspace pointing at the
    #    control plane must not become a write channel.
    link = os.path.join(layout.workspace, "escape-link.json")
    if os.path.lexists(link):
        os.unlink(link)
    os.symlink(os.path.join(layout.control, "registry.json"), link)
    rc, result, out, err = run_payload(["write", link], sandbox_profile=profile_path)
    record("symlink_escape_write", "denied", result, rc,
           note="a symlink in the writable area must not reach the control plane")

    # 5. Escape by changing permissions. Under seatbelt the kernel refuses the
    #    chmod itself; under plain POSIX bits the owner can chmod and then
    #    write, which is exactly the "only guards against mistakes" weakness.
    chmod_target = os.path.join(layout.control, "registry.json")
    rc, result, out, err = run_payload(["chmod", chmod_target, "--mode", "0o644"],
                                       sandbox_profile=profile_path)
    chmod_outcome = outcome_of(result)
    chmod_refused = chmod_outcome == "refused"
    if chmod_outcome != "refused":
        # The chmod went through: the boundary is weaker than a real one.
        rc2, result2, out2, err2 = run_payload(["write", chmod_target],
                                                sandbox_profile=profile_path)
        followup_outcome = outcome_of(result2)
        followup_refused = followup_outcome == "refused"
        checks.append({
            "check": "chmod_escape_write",
            "expected": "denied",
            "observed": followup_outcome,
            "errno": (result2 or {}).get("errno"),
            "errno_name": (result2 or {}).get("errno_name"),
            "child_exit_code": rc2,
            "ok": bool(followup_refused),
            "note": "owner changed the mode and then wrote the control plane",
        })
    else:
        checks.append({
            "check": "chmod_escape",
            "expected": "denied",
            "observed": "refused",
            "errno": (result or {}).get("errno"),
            "errno_name": (result or {}).get("errno_name"),
            "child_exit_code": rc,
            "ok": True,
            "note": "the boundary refused the permission change itself",
        })

    # 6. Negative control: the same write, with the control plane left
    #    writable, must now succeed. It runs outside the sandbox on purpose:
    #    this is the check that the verdict above came from the child's real
    #    behaviour and not from a static path list. When the control plane is
    #    read-only the write is refused, and that refusal is reported too, so
    #    the control cannot pass by accident.
    if args.control_permissions == "keep":
        control_target = os.path.join(layout.control, "registry.json")
        rc, result, out, err = run_payload(["write", control_target])
        control_outcome = outcome_of(result)
        written = control_outcome == "written" and rc == 0
        checks.append({
            "check": "negative_control_write",
            "expected": "written",
            "observed": control_outcome,
            "errno": (result or {}).get("errno"),
            "errno_name": (result or {}).get("errno_name"),
            "child_exit_code": rc,
            "ok": written,
            "note": "outside the sandbox, with write permission restored, the same "
                    "write must succeed; if it is refused the control plane was "
                    "still read-only and this control proves nothing",
        })

    after = layout.control_bytes()

    # 7. The control-plane bytes must be unchanged. This is what makes the
    #    check independent of the path strings used above.
    unchanged = before == after
    changed_files = sorted(
        name for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    checks.append({
        "check": "control_plane_bytes_unchanged",
        "expected": "unchanged",
        "observed": "unchanged" if unchanged else "changed",
        "child_exit_code": None,
        "ok": unchanged,
        "note": "sha256 of every control-plane file, before and after the probe",
    })

    failed = [c for c in checks if not c["ok"]]
    verdict = "PASS" if not failed else "FAIL"

    by_name = {c["check"]: c for c in checks}
    bytes_check = by_name["control_plane_bytes_unchanged"]
    naive_denials = [
        c for c in checks
        if c["expected"] == "denied" and c["check"] != "chmod_escape_write"
    ]
    denials_effective = all(c["ok"] for c in naive_denials)
    escape = by_name.get("chmod_escape_write")
    escape_succeeded = bool(escape and not escape["ok"])

    weak = False
    if args.control_permissions == "keep":
        # In keep mode the control plane is deliberately writable, so a
        # changed digest is expected only when a denial has actually failed
        # (as on posix, where the direct write goes through). When every
        # denial still holds (as under seatbelt), a changed digest means the
        # boundary leaked bytes despite the refusals: that must stay a
        # failure and can never be reported as kernel-enforced PASS.
        if denials_effective:
            bytes_check["ok"] = unchanged
            bytes_check["note"] = (
                "keep mode: every denial still held, so a changed control-plane "
                "digest is NOT expected and must fail; bytes changed: "
                + (", ".join(changed_files) if changed_files else "none")
            )
        else:
            bytes_check["ok"] = True
            bytes_check["note"] = (
                "keep mode: the control plane is deliberately writable, so a changed "
                "digest is expected here; the direct write check above is the one "
                "that must fail"
            )
        failed = [c for c in checks if not c["ok"]]
        verdict = "PASS" if not failed else "FAIL"
    elif verdict == "FAIL" and backend == "posix" and denials_effective and escape_succeeded:
        # WEAK: every naive write was denied, but the owner changed the mode
        # and got in. POSIX permission bits only guard against mistakes; they
        # are not an H1 enforcement boundary.
        weak = True
        verdict = "WEAK"

    report = {
        "schema_version": "isolation-probe-write/v1",
        "backend": backend,
        "root": layout.root,
        "checks": checks,
        "changed_control_files": changed_files,
        "control_before": before,
        "control_after": after,
        "verdict": verdict,
        "strength": (
            "kernel-enforced" if verdict == "PASS"
            else "guard-against-mistakes-only" if weak
            else "not-enforced"
        ),
    }
    if weak:
        report["weak_reason"] = (
            "every naive write was denied by the filesystem, but the owner could "
            "change the mode and then write the control plane; POSIX permission "
            "bits are not an H1 enforcement boundary"
        )
    return report


REQUIRED_POLICY_KEYS = ("senders", "stages", "reserved_tools")


def load_policy(path):
    """Load and validate the tool policy.

    The policy is the authority. If the caller can rewrite it, the identity
    binding it expresses cannot be trusted, so this refuses to judge.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as error:
        raise ProbeError(f"cannot read policy: {error.strerror}") from None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ProbeError("policy is not valid UTF-8 JSON") from None
    if not isinstance(data, dict):
        raise ProbeError("policy must be a JSON object")
    for key in REQUIRED_POLICY_KEYS:
        if key not in data:
            raise ProbeError(f"policy is missing {key}")
    if not isinstance(data["senders"], dict) or not data["senders"]:
        raise ProbeError("policy senders must be a non-empty object")
    for name, sender in data["senders"].items():
        if not isinstance(sender, dict):
            raise ProbeError(f"sender {name} must be an object")
        if "uid" not in sender:
            raise ProbeError(f"sender {name} has no uid")
        # A missing ceiling is not "unlimited": a policy that omits the
        # stage ceiling cannot be judged, and a non-numeric one would crash
        # the comparison later with a traceback on exit code 1 - the same
        # code as "this call is denied". Both are "the probe cannot run".
        max_stage = sender.get("max_stage")
        if max_stage is None:
            raise ProbeError(f"sender {name} has no max_stage")
        if isinstance(max_stage, bool) or not isinstance(max_stage, (int, float)):
            raise ProbeError(f"sender {name} max_stage must be a number")
        expires = sender.get("expires_at")
        if expires is not None and (isinstance(expires, bool)
                                    or not isinstance(expires, (int, float))):
            raise ProbeError(f"sender {name} expires_at must be a number or null")
    if not isinstance(data["stages"], dict):
        raise ProbeError("policy stages must be an object")
    # Stage keys are strings in JSON; the CLI passes an integer. Normalise
    # once here so every later lookup compares like with like.
    data["stages"] = {str(key): value for key, value in data["stages"].items()}
    for stage_spec in data["stages"].values():
        if not isinstance(stage_spec, dict) or not isinstance(stage_spec.get("tools"), list):
            raise ProbeError("each policy stage needs a tools list")
    return data


def policy_is_caller_writable(path):
    """True when the caller could rewrite the policy, now or after a chmod.

    A policy the caller can change is not an authority: the caller could
    simply add itself to the whitelist. Three ways of getting write access
    all count as writable:

      * the caller owns the file or its directory - an owner can always
        chmod the object back to writable and then rewrite it, so a
        same-uid 0o400/0o500 lock-down is NOT holder separation;
      * the caller has actual write access right now (write bits granted
        to a class the caller belongs to, checked with access(2));
      * the file or its directory cannot be stat-ed - nothing to verify.

    Both the file and its directory are checked, because a writable
    directory lets a caller swap the file. A policy owned by somebody else
    with no write access for the caller's classes (a conventional
    root-owned 0644 file in a 0755 directory) is NOT caller-writable.
    """
    reasons = []
    uid = os.getuid()
    try:
        info = os.stat(path)
    except OSError:
        return True, ["policy file is missing"]
    if info.st_uid == uid:
        reasons.append(
            "policy file is owned by the caller, who can chmod it writable and rewrite it"
        )
    elif os.access(path, os.W_OK):
        reasons.append("policy file is writable by the caller")
    directory = os.path.dirname(os.path.abspath(path))
    try:
        dinfo = os.stat(directory)
    except OSError:
        return True, ["policy directory is missing"]
    if dinfo.st_uid == uid:
        reasons.append(
            "policy directory is owned by the caller, who can chmod it writable and swap the file"
        )
    elif os.access(directory, os.W_OK):
        reasons.append("policy directory is writable by the caller")
    return bool(reasons), reasons


def effective_sender(policy, uid, gid):
    """Find the sender bound to the real process identity.

    The binding comes from the policy, keyed by the uid/gid the process
    actually runs as. Anything the caller says about itself is ignored.
    """
    for name, sender in policy["senders"].items():
        if sender.get("uid") == uid and sender.get("gid") == gid:
            return name, sender
    return None, None


def decide_tool_call(policy, sender, tool, stage, now):
    """Decide one tool call. Returns (allowed, reason).

    Every refusal below is a rule about the sender's own bound record, never
    about a claim made in the request.
    """
    if sender is None:
        return False, "unknown-sender: this process identity is not bound in the policy"

    tools = sender.get("tools", [])
    if tool not in tools:
        return False, "tool-not-in-sender-scope"

    # The stage has to exist in the policy before it can be compared with the
    # sender's ceiling: a stage the policy never mentions is not a stage
    # escalation, it is an unknown stage.
    stage_key = str(stage)
    if stage_key not in policy["stages"]:
        return False, "stage-not-in-policy"

    max_stage = sender.get("max_stage")
    if max_stage is not None and stage > max_stage:
        return False, "stage-above-sender-max-stage"

    stage_tools = policy["stages"][stage_key].get("tools", [])
    if tool not in stage_tools:
        return False, "tool-not-in-stage-whitelist"

    if tool in policy.get("reserved_tools", []):
        return False, "reserved-tool-never-authorized"

    expires = sender.get("expires_at")
    if expires is not None and now > expires:
        return False, "sender-authorization-expired"

    return True, "allowed"


def probe_tool(args):
    """E03. Judge a tool call and let the exit code be the gate."""
    policy = load_policy(args.policy)
    writable, reasons = policy_is_caller_writable(args.policy)
    if writable and not args.allow_writable_policy:
        report = {
            "schema_version": "isolation-probe-tool/v1",
            "verdict": "REFUSED_TO_JUDGE",
            "reason": "policy is writable by the caller, so its identity binding cannot be trusted",
            "policy_writable_reasons": reasons,
            "allowed": False,
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 5

    uid = os.getuid()
    gid = os.getgid()
    sender_name, sender = effective_sender(policy, uid, gid)
    now = args.now if args.now is not None else time.time()

    allowed, reason = decide_tool_call(policy, sender, args.tool, args.stage, now)

    report = {
        "schema_version": "isolation-probe-tool/v1",
        "verdict": "ALLOW" if allowed else "DENY",
        "reason": reason,
        "allowed": allowed,
        "process_uid": uid,
        "process_gid": gid,
        "sender": sender_name,
        "requested_tool": args.tool,
        "requested_stage": args.stage,
        "claimed_sender": args.claimed_sender,
        "claimed_tool": args.claimed_tool,
        "claimed_stage": args.claimed_stage,
        "claim_used_for_decision": False,
        "stage_whitelist": policy["stages"].get(str(args.stage), {}).get("tools", []),
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    # The exit code is the gate: 0 allows, 1 denies.
    return 0 if allowed else 1


def readback_whitelist(policy, stage, now):
    """The effective tool whitelist for a stage.

    A tool is effective only when the stage allows it AND every bound sender
    that could call it allows it. Reading this back is what the E03 gate
    asks for: the whitelist that is actually in force, per stage.
    """
    stage_tools = policy["stages"].get(str(stage), {}).get("tools", [])
    effective = []
    for tool in stage_tools:
        if tool in policy.get("reserved_tools", []):
            continue
        usable = False
        for name, sender in policy["senders"].items():
            if tool in sender.get("tools", []):
                # The same expiration predicate the gate uses: a sender
                # whose authorization has lapsed must not make a tool look
                # usable in the effective whitelist.
                expires = sender.get("expires_at")
                if expires is not None and now > expires:
                    continue
                max_stage = sender.get("max_stage")
                if max_stage is None or stage <= max_stage:
                    usable = True
                    break
        if usable:
            effective.append(tool)
    return effective


def probe_readback(args):
    """E03. Read back the tool whitelist that is actually in force."""
    policy = load_policy(args.policy)
    writable, reasons = policy_is_caller_writable(args.policy)
    if writable and not args.allow_writable_policy:
        print(json.dumps({
            "schema_version": "isolation-probe-readback/v1",
            "verdict": "REFUSED_TO_JUDGE",
            "reason": "policy is writable by the caller",
            "policy_writable_reasons": reasons,
        }, ensure_ascii=False, sort_keys=True))
        return 5
    now = args.now if args.now is not None else time.time()
    report = {
        "schema_version": "isolation-probe-readback/v1",
        "verdict": "OK",
        "stage": args.stage,
        "stage_whitelist": policy["stages"].get(str(args.stage), {}).get("tools", []),
        "effective_whitelist": readback_whitelist(policy, args.stage, now),
        "reserved_tools": policy.get("reserved_tools", []),
        "senders": {
            name: {
                "max_stage": sender.get("max_stage"),
                "tools": sender.get("tools", []),
            }
            for name, sender in policy["senders"].items()
        },
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


class _PrintVersion(argparse.Action):
    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        sys.stdout.write(tool_fingerprint() + "\n")
        parser.exit(0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action=_PrintVersion)
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write", help="E02: real write-isolation probe")
    write.add_argument("--root", required=True, help="directory that holds the four roots")
    write.add_argument("--backend", choices=["seatbelt", "posix"], default="seatbelt")
    write.add_argument("--fresh", action="store_true", help="rebuild the layout first")
    write.add_argument("--control-permissions", choices=["tighten", "keep"], default="tighten",
                       help="tighten: make the control plane read-only; keep: leave it "
                            "writable so the negative control can show the write is real")

    tool = sub.add_parser("tool", help="E03: decide one tool call")
    tool.add_argument("--policy", required=True)
    tool.add_argument("--tool", required=True)
    tool.add_argument("--stage", type=int, required=True)
    tool.add_argument("--now", type=float, default=None)
    tool.add_argument("--claimed-sender", default=None)
    tool.add_argument("--claimed-tool", default=None)
    tool.add_argument("--claimed-stage", type=int, default=None)
    tool.add_argument("--allow-writable-policy", action="store_true",
                      help="testing only: judge even though the policy is writable")

    readback = sub.add_parser("readback", help="E03: read back the effective whitelist")
    readback.add_argument("--policy", required=True)
    readback.add_argument("--stage", type=int, required=True)
    readback.add_argument("--now", type=float, default=None)
    readback.add_argument("--allow-writable-policy", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "write":
        try:
            report = probe_write(args)
        except ProbeError as error:
            print(json.dumps({"verdict": "PROBE_ERROR", "reason": str(error)},
                             ensure_ascii=False, sort_keys=True))
            return 5
        except OSError as error:
            # The probe could not set the boundary up (a root it cannot
            # replace, a filesystem that refuses). That is "the probe did
            # not run", not "the boundary failed": report it as such
            # instead of raising a traceback that prints no verdict.
            print(json.dumps({
                "verdict": "PROBE_ERROR",
                "reason": f"the probe could not prepare the layout: {error}",
            }, ensure_ascii=False, sort_keys=True))
            return 5
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        if report["verdict"] == "PASS":
            return 0
        if report["verdict"] == "WEAK":
            return 3
        return 1

    if args.command == "tool":
        try:
            return probe_tool(args)
        except ProbeError as error:
            print(json.dumps({"verdict": "PROBE_ERROR", "reason": str(error)},
                             ensure_ascii=False, sort_keys=True))
            return 5

    try:
        return probe_readback(args)
    except ProbeError as error:
        print(json.dumps({"verdict": "PROBE_ERROR", "reason": str(error)},
                         ensure_ascii=False, sort_keys=True))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
