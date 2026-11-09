"""C6 loop-closure detector v1: verify closure evidence, never the summary.

Pure function: reads bytes, no network, no clock, no filesystem writes, stdlib
only. Closure (exit 0) can only come from complete step evidence; a report
status of "closed" is recorded but never trusted (it is echoed as
status_ignored). Every failure mode found is listed once, deterministically.
"""
import hashlib
import json
import re
import sys

VERSION = "v1"
SCHEMA = "loop-closure/v1"
MAX_BYTES = 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[^\s]{1,128}")


class InputError(ValueError):
    pass


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON key")
        result[key] = value
    return result


def load(raw, what):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise InputError(f"expected bounded non-empty {what} bytes")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise InputError(f"invalid {what} JSON bytes") from None


def nonempty(value):
    return isinstance(value, str) and bool(value) and value == value.strip()


def parse_report(raw):
    report = load(raw, "report")
    if not isinstance(report, dict) or set(report) != {
            "schema_version", "head_sha", "producer", "verifier", "status",
            "loops", "steps"}:
        raise InputError("report fields mismatch")
    if report["schema_version"] != SCHEMA:
        raise InputError("unsupported schema_version")
    for key in ("head_sha",):
        if not isinstance(report[key], str) or not re.fullmatch(r"[0-9a-f]{40}", report[key]):
            raise InputError(f"invalid {key}")
    for key in ("producer", "status"):
        if not nonempty(report[key]):
            raise InputError(f"invalid {key}")
    if not isinstance(report["verifier"], str):
        raise InputError("invalid verifier")
    if not isinstance(report["loops"], list) or not report["loops"] or \
            any(not nonempty(x) for x in report["loops"]) or \
            len({x for x in report["loops"]}) != len(report["loops"]):
        raise InputError("invalid loops")
    steps = report["steps"]
    if not isinstance(steps, list):
        raise InputError("steps must be a list")
    for step in steps:
        if not isinstance(step, dict) or set(step) != {
                "id", "command", "exit_code", "output_sha256", "citations"}:
            raise InputError("step fields mismatch")
        if not nonempty(step["id"]) or not ID.fullmatch(step["id"]):
            raise InputError("invalid step id")
        command = step["command"]
        if not isinstance(command, list) or not command or \
                any(not isinstance(a, str) or not a for a in command):
            raise InputError("invalid step command")
        if type(step["exit_code"]) is not int:
            raise InputError("invalid step exit code")
        if not isinstance(step["output_sha256"], str) or not SHA.fullmatch(step["output_sha256"]):
            raise InputError("invalid step output digest")
        if not isinstance(step["citations"], list):
            raise InputError("citations must be a list")
        for cite in step["citations"]:
            if not isinstance(cite, dict) or set(cite) != {"path", "line", "excerpt"}:
                raise InputError("citation fields mismatch")
            if not nonempty(cite["path"]) or not isinstance(cite["excerpt"], str):
                raise InputError("invalid citation")
            if type(cite["line"]) is not int:
                raise InputError("invalid citation line")
    if len({s["id"] for s in steps}) != len(steps):
        raise InputError("duplicate step id")
    return report


def file_lines(raw, path):
    if not isinstance(raw, bytes):
        raise InputError("file bytes required")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError(f"cited file not utf-8: {path}") from None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def assess(report_raw, files, outputs, expected_head_sha, previous_loop_ids):
    """Return (exit_code, canonical_json_bytes). 0 verified, 1 findings, 5 input error."""
    try:
        report = parse_report(report_raw)
        if not isinstance(files, dict) or any(not isinstance(k, str) or not isinstance(v, bytes)
                                              for k, v in files.items()):
            raise InputError("files must map path to bytes")
        if not isinstance(outputs, dict) or any(not isinstance(k, str) or not isinstance(v, bytes)
                                                for k, v in outputs.items()):
            raise InputError("outputs must map step id to bytes")
        if not isinstance(expected_head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_head_sha):
            raise InputError("trusted expected head sha (40-hex git commit sha) required")
        if not isinstance(previous_loop_ids, list) or \
                any(not nonempty(x) for x in previous_loop_ids) or \
                len(set(previous_loop_ids)) != len(previous_loop_ids):
            raise InputError("invalid previous loop ids")
        findings = []
        if not report["steps"]:
            findings.append({"finding": "empty_steps",
                             "detail": "closure claim has no steps; a summary status is not evidence"})
        verifier, producer = report["verifier"].strip(), report["producer"].strip()
        if not verifier:
            findings.append({"finding": "verifier_not_independent",
                             "detail": "missing verifier"})
        elif verifier.casefold() == producer.casefold():
            findings.append({"finding": "verifier_not_independent",
                             "detail": f"verifier {verifier!r} equals producer {producer!r}"})
        if report["head_sha"] != expected_head_sha:
            findings.append({"finding": "stale_head_sha",
                             "detail": f"report head {report['head_sha']} != expected {expected_head_sha}"})
        for loop_id in sorted(set(previous_loop_ids) - set(report["loops"])):
            findings.append({"finding": "history_deleted",
                             "detail": f"previously reported loop absent from current report: {loop_id}"})
        for step in report["steps"]:
            sid = step["id"]
            if step["exit_code"] != 0:
                findings.append({"finding": "step_failed", "detail": f"{sid} exit_code {step['exit_code']}"})
            raw = outputs.get(sid)
            if raw is None:
                findings.append({"finding": "missing_output", "detail": f"no output bytes for {sid}"})
            elif hashlib.sha256(raw).hexdigest() != step["output_sha256"]:
                findings.append({"finding": "output_digest_mismatch", "detail": sid})
            for cite in step["citations"]:
                path, line, excerpt = cite["path"], cite["line"], cite["excerpt"]
                if path not in files:
                    findings.append({"finding": "missing_cited_file", "detail": f"{sid} cites absent file {path}"})
                    continue
                lines = file_lines(files[path], path)
                if not 1 <= line <= len(lines):
                    findings.append({"finding": "line_out_of_range",
                                     "detail": f"{sid} cites {path}:{line}, file has {len(lines)} lines"})
                elif lines[line - 1] != excerpt:
                    findings.append({"finding": "misquoted_line",
                                     "detail": f"{sid} cites {path}:{line} but the excerpt does not match"})
        code = 0 if not findings else 1
        result = {"schema_version": SCHEMA, "head_sha": report["head_sha"],
                  "loops": sorted(report["loops"]),
                  "status_ignored": report["status"],
                  "findings": findings,
                  "result": "CLOSED_VERIFIED" if code == 0 else "NOT_CLOSED",
                  "scope": "report evidence only; no identity authentication or stage changes"}
        return code, canonical(result)
    except Exception as error:
        return 5, canonical({"result": "INPUT_ERROR", "reason": str(error)})


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["--version"]:
        with open(__file__, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        print(f"{VERSION} {digest}")
        return 0
    print("usage: detect.py --version  (assessment is a library function)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
