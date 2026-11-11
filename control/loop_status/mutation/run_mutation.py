#!/usr/bin/env python3
"""Apply mutmut 3.3.1 operators to history.py and record unittest results.

The classification rules live in equivalent-mutant-definition.md. This
script has no branch that labels a mutant equivalent.
"""
from __future__ import annotations

import argparse
import atexit
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFINITION = Path(__file__).resolve().parent / "equivalent-mutant-definition.md"
REQUIREMENTS = Path(__file__).resolve().parent / "requirements.txt"
TARGET_REL = "control/loop_status/history.py"
TESTS_REL = "control/loop_status/tests/test_history.py"
FREEZE_LINE = re.compile(r"^FREEZE ([A-Z0-9_]+)=(.*)$")
REQUIRED_FREEZE = (
    "TARGET",
    "HISTORY_SHA256",
    "RUN1_TESTS_SHA256",
    "TOOL",
    "TOOL_VERSION",
    "LIBCST_VERSION",
    "REQUIREMENTS_SHA256",
    "TIMEOUT_SECONDS",
    "EQUIVALENT_PATTERNS",
    "KILL_RATE",
)
OUTPUT_CAP = 32768
_restore: tuple[Path, bytes] | None = None


def _emergency_restore() -> None:
    if _restore is None:
        return
    path, data = _restore
    path.write_bytes(data)


atexit.register(_emergency_restore)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_freeze(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = FREEZE_LINE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key in found:
            raise SystemExit(f"duplicate FREEZE key {key}")
        found[key] = value
    missing = [key for key in REQUIRED_FREEZE if key not in found]
    if missing:
        raise SystemExit("definition missing FREEZE keys: " + ", ".join(missing))
    return found


def unified(original: str, mutant: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            mutant.splitlines(keepends=True),
            fromfile=TARGET_REL,
            tofile=TARGET_REL + " (mutant)",
        )
    )


def run_suite(timeout: int) -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("MUTANT_UNDER_TEST", None)
    command = [sys.executable, "-m", "unittest", "discover", "-s", "control/loop_status/tests", "-q"]
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            timeout=timeout,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - started
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        return {
            "status": "timeout",
            "exit_code": None,
            "duration_seconds": round(duration, 6),
            "stdout": stdout,
            "stderr": stderr,
        }
    duration = time.perf_counter() - started
    status = "survived" if proc.returncode == 0 else "killed"
    return {
        "status": status,
        "exit_code": proc.returncode,
        "duration_seconds": round(duration, 6),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def clip_output(stdout: bytes, stderr: bytes) -> dict:
    out = stdout.decode("utf-8", "replace")
    err = stderr.decode("utf-8", "replace")
    raw = out + ("\n" if out and err else "") + err
    digest = sha256_bytes(raw.encode("utf-8"))
    truncated = len(raw) > OUTPUT_CAP
    return {
        "output_sha256": digest,
        "output_truncated": truncated,
        "output": raw[:OUTPUT_CAP],
    }


def meets_bar(killed: int, valid: int) -> bool:
    return valid >= 20 and killed * 20 >= valid * 19


def rate_text(killed: int, valid: int) -> str:
    if valid == 0:
        return ""
    from decimal import Decimal, ROUND_HALF_UP

    quant = (Decimal(killed) / Decimal(valid)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return format(quant, "f")


def git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expect-tests-sha256", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"run[1-9][0-9]*", args.run_id):
        print("run-id must look like run1", file=sys.stderr)
        return 1

    freeze = load_freeze(DEFINITION)
    if freeze["TOOL"] != "mutmut" or freeze["EQUIVALENT_PATTERNS"] != "none":
        print("refusing to run: equivalent-pattern freeze is not the empty set", file=sys.stderr)
        return 1
    if freeze["KILL_RATE"] != "killed/(killed+survived+timeout)":
        print("refusing to run: kill-rate formula was edited", file=sys.stderr)
        return 1
    if freeze["TARGET"] != TARGET_REL:
        print("refusing to run: target was edited", file=sys.stderr)
        return 1
    timeout = int(freeze["TIMEOUT_SECONDS"])
    if timeout != 10:
        print("refusing to run: timeout freeze is not 10", file=sys.stderr)
        return 1

    try:
        tool_version = version("mutmut")
        libcst_version = version("libcst")
    except PackageNotFoundError as exc:
        print(f"missing package: {exc}", file=sys.stderr)
        return 1
    if tool_version != freeze["TOOL_VERSION"] or libcst_version != freeze["LIBCST_VERSION"]:
        print(
            f"version mismatch mutmut={tool_version} libcst={libcst_version}",
            file=sys.stderr,
        )
        return 1
    requirements_hash = sha256_bytes(REQUIREMENTS.read_bytes())
    if requirements_hash != freeze["REQUIREMENTS_SHA256"]:
        print("requirements.txt hash mismatch", file=sys.stderr)
        return 1

    target = ROOT / TARGET_REL
    tests = ROOT / TESTS_REL
    original = target.read_bytes()
    history_hash = sha256_bytes(original)
    tests_hash = sha256_bytes(tests.read_bytes())
    if history_hash != freeze["HISTORY_SHA256"]:
        print("history.py hash mismatch", file=sys.stderr)
        return 1
    if args.expect_tests_sha256 != tests_hash:
        print("test file hash does not match --expect-tests-sha256", file=sys.stderr)
        return 1
    if args.run_id == "run1" and tests_hash != freeze["RUN1_TESTS_SHA256"]:
        print("run1 test file hash does not match the freeze", file=sys.stderr)
        return 1

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    if (output / "report.json").exists():
        print("report.json already exists; refusing to overwrite", file=sys.stderr)
        return 1

    global _restore
    _restore = (target, original)

    baseline = run_suite(timeout)
    baseline_text = clip_output(baseline["stdout"], baseline["stderr"])
    (output / "baseline.txt").write_text(
        f"exit_code={baseline['exit_code']}\nstatus={baseline['status']}\n"
        f"duration_seconds={baseline['duration_seconds']}\n"
        f"output_sha256={baseline_text['output_sha256']}\n"
        f"{baseline_text['output']}",
        encoding="utf-8",
    )
    if baseline["status"] != "survived":
        print("baseline tests did not exit 0", file=sys.stderr)
        return 1

    from mutmut.file_mutation import create_mutations, deep_replace

    source = original.decode("utf-8")
    module, mutations = create_mutations(source)
    events = output / "events.jsonl"
    counts = {"killed": 0, "survived": 0, "timeout": 0, "invalid": 0}
    invalid_reasons = {"I1_syntax": 0, "I2_identical": 0, "I3_apply_error": 0}
    rows: list[dict] = []

    with events.open("w", encoding="utf-8") as stream:
        for index, mutation in enumerate(mutations, 1):
            mutant_id = f"m{index:04d}"
            node_type = type(mutation.original_node).__name__
            row: dict = {"id": mutant_id, "node_type": node_type}
            try:
                mutated = deep_replace(module, mutation.original_node, mutation.mutated_node).code
            except Exception as exc:
                row.update(status="invalid", reason="I3_apply_error", error=f"{type(exc).__name__}: {exc}")
                counts["invalid"] += 1
                invalid_reasons["I3_apply_error"] += 1
            else:
                if mutated == source:
                    row.update(status="invalid", reason="I2_identical", diff="")
                    counts["invalid"] += 1
                    invalid_reasons["I2_identical"] += 1
                else:
                    try:
                        compile(mutated, TARGET_REL, "exec")
                    except (SyntaxError, IndentationError) as exc:
                        row.update(
                            status="invalid",
                            reason="I1_syntax",
                            error=f"{type(exc).__name__}: {exc}",
                            diff=unified(source, mutated),
                        )
                        counts["invalid"] += 1
                        invalid_reasons["I1_syntax"] += 1
                    else:
                        wrote = False
                        try:
                            target.write_bytes(mutated.encode("utf-8"))
                            wrote = True
                            outcome = run_suite(timeout)
                        finally:
                            if wrote:
                                target.write_bytes(original)
                                if target.read_bytes() != original:
                                    print("failed to restore history.py", file=sys.stderr)
                                    return 1
                        shown = clip_output(outcome["stdout"], outcome["stderr"])
                        row.update(
                            status=outcome["status"],
                            exit_code=outcome["exit_code"],
                            duration_seconds=outcome["duration_seconds"],
                            diff=unified(source, mutated),
                            **shown,
                        )
                        counts[outcome["status"]] += 1
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            print(f"{index}/{len(mutations)} {row['status']} {mutant_id}", file=sys.stderr)

    if target.read_bytes() != original:
        print("history.py differs after the run", file=sys.stderr)
        return 1
    _restore = None

    generated = len(rows)
    valid = counts["killed"] + counts["survived"] + counts["timeout"]
    if generated != len(mutations) or valid + counts["invalid"] != generated:
        print("count invariant failed", file=sys.stderr)
        return 1
    if [row["id"] for row in rows] != [f"m{i:04d}" for i in range(1, generated + 1)]:
        print("mutant ids are not contiguous", file=sys.stderr)
        return 1
    if any(row["status"] == "equivalent" for row in rows):
        print("equivalent status is not allowed", file=sys.stderr)
        return 1

    bar = meets_bar(counts["killed"], valid)
    report = {
        "schema": "mutation-report/v1",
        "run_id": args.run_id,
        "tool": "mutmut",
        "tool_version": tool_version,
        "tool_api": "mutmut.file_mutation.create_mutations + deep_replace",
        "libcst_version": libcst_version,
        "python": sys.version,
        "git_head": git_head(),
        "definition_sha256": sha256_bytes(DEFINITION.read_bytes()),
        "requirements_sha256": requirements_hash,
        "target": TARGET_REL,
        "target_sha256": history_hash,
        "tests_sha256": tests_hash,
        "timeout_seconds": timeout,
        "equivalent_patterns": "none",
        "test_command": [sys.executable, "-m", "unittest", "discover", "-s", "control/loop_status/tests", "-q"],
        "baseline_exit_code": baseline["exit_code"],
        "counts": {
            "generated": generated,
            "invalid": counts["invalid"],
            "invalid_reasons": invalid_reasons,
            "equivalent": 0,
            "killed": counts["killed"],
            "survived": counts["survived"],
            "timeout": counts["timeout"],
            "valid": valid,
        },
        "kill_rate": {
            "formula": "killed/(killed+survived+timeout)",
            "killed": counts["killed"],
            "valid": valid,
            "fraction": f"{counts['killed']}/{valid}",
            "rounded_6dp": rate_text(counts["killed"], valid),
            "bar_min_valid": 20,
            "bar_min_kill_rate": "0.95",
            "bar_integer_test": "killed * 20 >= valid * 19",
            "bar_met": bar,
        },
        "mutants": rows,
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    survived = [row["id"] for row in rows if row["status"] == "survived"]
    timed_out = [row["id"] for row in rows if row["status"] == "timeout"]
    invalid_ids = [row["id"] for row in rows if row["status"] == "invalid"]
    lines = [
        f"run_id: {args.run_id}",
        f"tool: mutmut {tool_version}",
        "tool_api: mutmut.file_mutation.create_mutations + deep_replace",
        f"libcst: {libcst_version}",
        f"python: {sys.version.split()[0]}",
        f"git_head: {report['git_head']}",
        f"definition_sha256: {report['definition_sha256']}",
        f"target: {TARGET_REL}",
        f"target_sha256: {history_hash}",
        f"tests_sha256: {tests_hash}",
        f"timeout_seconds: {timeout}",
        f"baseline_exit_code: {baseline['exit_code']}",
        f"generated: {generated}",
        f"invalid: {counts['invalid']}",
        f"invalid_I1_syntax: {invalid_reasons['I1_syntax']}",
        f"invalid_I2_identical: {invalid_reasons['I2_identical']}",
        f"invalid_I3_apply_error: {invalid_reasons['I3_apply_error']}",
        "equivalent: 0",
        f"killed: {counts['killed']}",
        f"survived: {counts['survived']}",
        f"timeout: {counts['timeout']}",
        f"valid: {valid}",
        f"kill_rate: {counts['killed']}/{valid}",
        f"kill_rate_rounded_6dp: {rate_text(counts['killed'], valid)}",
        f"bar_met: {'yes' if bar else 'no'}",
        "equivalent_patterns: none",
        "survived_ids: " + (" ".join(survived) if survived else "-"),
        "timeout_ids: " + (" ".join(timed_out) if timed_out else "-"),
        "invalid_ids: " + (" ".join(invalid_ids) if invalid_ids else "-"),
    ]
    summary = "\n".join(lines) + "\n"
    (output / "summary.txt").write_text(summary, encoding="utf-8")
    sys.stdout.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
