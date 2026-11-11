"""Map coverage and author/verifier independence (loop-map/v1).

Pure function: no clock, no network, no filesystem, stdlib only. Exit 0 means
this call found no map-coverage or independence finding. It does not mean a
loop is closed, and it does not call the history ratchet.
"""
import hashlib
import importlib.util
import json
import re
from pathlib import Path

MAX_BYTES = 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}")
STEP_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
SCHEMA = "loop-map-check/v1"
SCOPE = (
    "map coverage and independence only; exit 0 is not loop closure, "
    "not a history ratchet result, and not a stage change"
)


class InputError(ValueError):
    pass


def _load_detect():
    path = Path(__file__).resolve().with_name("detect.py")
    spec = importlib.util.spec_from_file_location("loop_closure_detect_for_map", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_DETECT = _load_detect()
normalize_name = _DETECT.normalize_name


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON key")
        result[key] = value
    return result


def load_json(raw, what):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise InputError(f"expected bounded non-empty {what} bytes")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise InputError(f"invalid {what} JSON bytes") from None


def alias_table(aliases):
    """Map a normalized spelling to one canonical id.

    None means "compare normalized strings only". A dict is caller-supplied
    configuration, never read from the map under review. Cf characters are
    removed and NFKC is applied before casefold, same as detect.normalize_name.
    """
    if aliases is None:
        return None
    if not isinstance(aliases, dict) or not aliases:
        raise InputError("invalid alias configuration")
    table = {}
    for stable, names in aliases.items():
        if not isinstance(names, list):
            raise InputError("invalid alias configuration")
        canonical_id = normalize_name(stable) if isinstance(stable, str) else ""
        if not canonical_id:
            raise InputError("invalid identity")
        for form in [stable, *names]:
            if not isinstance(form, str):
                raise InputError("invalid alias")
            key = normalize_name(form)
            if not key:
                raise InputError("invalid alias")
            previous = table.get(key)
            if previous is not None and previous != canonical_id:
                raise InputError("ambiguous alias")
            table[key] = canonical_id
    return table


def identity(value, table, label):
    if not isinstance(value, str):
        raise InputError(f"invalid {label}")
    key = normalize_name(value)
    if not key:
        return ""
    if table is None:
        return key
    if key not in table:
        raise InputError(f"unknown {label}")
    return table[key]


def valid_command(command):
    if isinstance(command, str):
        return bool(command.strip())
    return (isinstance(command, list) and bool(command)
            and all(isinstance(part, str) and part for part in command))


def parse_map(raw):
    document = load_json(raw, "map")
    if not isinstance(document, dict) or set(document) != {"schema_version", "author", "verifier", "steps"}:
        raise InputError("map fields mismatch")
    if document["schema_version"] != "loop-map/v1":
        raise InputError("unsupported map schema_version")
    if not isinstance(document["author"], str):
        raise InputError("invalid author")
    if not isinstance(document["verifier"], str):
        raise InputError("invalid verifier")
    steps = document["steps"]
    if not isinstance(steps, list):
        raise InputError("steps must be a list")
    seen = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"id", "command", "expected", "measured_source"}:
            raise InputError("step fields mismatch")
        if not isinstance(step["id"], str) or not STEP_ID.fullmatch(step["id"]):
            raise InputError("invalid step id")
        if step["id"] in seen:
            raise InputError("duplicate step id")
        seen.add(step["id"])
        if not valid_command(step["command"]):
            raise InputError("invalid step command")
        if not isinstance(step["expected"], str) or not step["expected"].strip():
            raise InputError("invalid step expected")
        if not isinstance(step["measured_source"], str):
            raise InputError("invalid measured_source")
    return document


def parse_receipt(raw):
    document = load_json(raw, "receipt")
    if not isinstance(document, dict) or set(document) != {"schema_version", "map_sha256", "steps"}:
        raise InputError("receipt fields mismatch")
    if document["schema_version"] != "loop-map-receipt/v1":
        raise InputError("unsupported receipt schema_version")
    if not isinstance(document["map_sha256"], str) or not HEX.fullmatch(document["map_sha256"]):
        raise InputError("invalid receipt map_sha256")
    steps = document["steps"]
    if not isinstance(steps, list):
        raise InputError("receipt steps must be a list")
    seen = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"id"}:
            raise InputError("receipt step fields mismatch")
        if not isinstance(step["id"], str) or not STEP_ID.fullmatch(step["id"]):
            raise InputError("invalid receipt step id")
        if step["id"] in seen:
            raise InputError("duplicate receipt step id")
        seen.add(step["id"])
    return document


def assess_map(map_raw, receipt_raw, expected_map_sha256, aliases=None):
    """Return (exit_code, canonical_json_bytes).

    0 NO_REGRESSION, 1 REGRESSION (findings), 5 INPUT_ERROR.
    Exit 0 is not loop closure.
    """
    try:
        document = parse_map(map_raw)
        receipt = parse_receipt(receipt_raw)
        if not isinstance(expected_map_sha256, str) or not HEX.fullmatch(expected_map_sha256):
            raise InputError("trusted map sha256 required")
        table = alias_table(aliases)
        author = identity(document["author"], table, "author")
        verifier = identity(document["verifier"], table, "verifier")
        digest = hashlib.sha256(map_raw).hexdigest()
        findings = []
        if not author:
            findings.append({"finding": "missing_author", "detail": "author normalizes to empty"})
        if not verifier:
            findings.append({"finding": "verifier_not_independent", "detail": "missing verifier"})
        elif author and author == verifier:
            findings.append({
                "finding": "author_alias_self_check",
                "detail": f"author {author!r} and verifier {verifier!r} are the same identity",
            })
        if not document["steps"]:
            findings.append({
                "finding": "empty_steps",
                "detail": "map has no steps; a summary status is not evidence",
            })
        for step in document["steps"]:
            if not normalize_name(step["measured_source"]):
                findings.append({"finding": "missing_measured_source", "detail": step["id"]})
        if digest != expected_map_sha256 or receipt["map_sha256"] != digest:
            findings.append({
                "finding": "stale_map_sha",
                "detail": f"bytes {digest} expected {expected_map_sha256} receipt {receipt['map_sha256']}",
            })
        map_ids = {step["id"] for step in document["steps"]}
        receipt_ids = {step["id"] for step in receipt["steps"]}
        for step_id in sorted(map_ids - receipt_ids):
            findings.append({"finding": "coverage_missing", "detail": step_id})
        for step_id in sorted(receipt_ids - map_ids):
            findings.append({"finding": "coverage_extra", "detail": step_id})
        findings.sort(key=lambda item: (item["finding"], item["detail"]))
        code = 0 if not findings else 1
        body = {
            "schema_version": SCHEMA,
            "map_sha256": digest,
            "findings": findings,
            "result": "NO_REGRESSION" if code == 0 else "REGRESSION",
            "scope": SCOPE,
        }
        return code, canonical(body)
    except Exception as error:
        return 5, canonical({"result": "INPUT_ERROR", "reason": str(error)})


CAPABILITY_SCOPE = (
    "capability feature-map coverage only; a NOT_TESTED verifier stays a finding; "
    "exit 0 is not loop closure, not a history ratchet result, and not a stage change"
)


def assess_capability_map(map_raw, receipt_raw=None, expected_map_sha256=None, aliases=None):
    """Check one on-disk feature map. Extra keys are allowed. Exit 0 is not closure.

    `measured_source` or `actual_source` counts as the measured-source field.
    A `tests` list does not. `author` or `producer` counts as the author.
    `independent_verification.status == NOT_TESTED` or a null verifier is a finding.
    """
    try:
        document = load_json(map_raw, "map")
        if not isinstance(document, dict):
            raise InputError("map must be an object")
        table = alias_table(aliases)
        findings = []
        author_value = document["author"] if "author" in document else document.get("producer")
        if not isinstance(author_value, str):
            author = ""
            findings.append({"finding": "missing_author", "detail": "feature map has no author or producer string"})
        else:
            author = identity(author_value, table, "author")
            if not author:
                findings.append({"finding": "missing_author", "detail": "author normalizes to empty"})
        block = document.get("independent_verification")
        verifier_value = block.get("verifier") if isinstance(block, dict) else None
        status = block.get("status") if isinstance(block, dict) else None
        if not isinstance(verifier_value, str) or status == "NOT_TESTED":
            verifier = ""
            findings.append({
                "finding": "verifier_not_independent",
                "detail": "missing verifier" if not isinstance(verifier_value, str) else "verification status is NOT_TESTED",
            })
        else:
            verifier = identity(verifier_value, table, "verifier")
            if not verifier:
                findings.append({"finding": "verifier_not_independent", "detail": "missing verifier"})
        if author and verifier and author == verifier:
            findings.append({
                "finding": "author_alias_self_check",
                "detail": f"author {author!r} and verifier {verifier!r} are the same identity",
            })
        steps = document.get("steps")
        map_ids = set()
        if not isinstance(steps, list) or not steps:
            findings.append({"finding": "empty_steps", "detail": "feature map has no steps"})
        else:
            for step in steps:
                if not isinstance(step, dict):
                    raise InputError("step must be an object")
                step_id = step.get("id")
                if not isinstance(step_id, str) or not STEP_ID.fullmatch(step_id) or step_id in map_ids:
                    raise InputError("invalid or duplicate step id")
                map_ids.add(step_id)
                if not valid_command(step.get("command")):
                    findings.append({"finding": "missing_command", "detail": step_id})
                expected = step.get("expected")
                if not isinstance(expected, str) or not expected.strip():
                    findings.append({"finding": "missing_expected", "detail": step_id})
                source = step["measured_source"] if "measured_source" in step else step.get("actual_source")
                if not isinstance(source, str) or not normalize_name(source):
                    findings.append({"finding": "missing_measured_source", "detail": step_id})
        digest = hashlib.sha256(map_raw).hexdigest()
        if expected_map_sha256 is None:
            findings.append({"finding": "stale_map_sha", "detail": f"trusted map sha256 absent for {digest}"})
        elif not isinstance(expected_map_sha256, str) or not HEX.fullmatch(expected_map_sha256):
            raise InputError("trusted map sha256 required")
        elif expected_map_sha256 != digest:
            findings.append({
                "finding": "stale_map_sha",
                "detail": f"bytes {digest} expected {expected_map_sha256}",
            })
        if receipt_raw is None:
            findings.append({"finding": "coverage_missing", "detail": "receipt absent"})
        else:
            receipt = parse_receipt(receipt_raw)
            if receipt["map_sha256"] != digest:
                findings.append({
                    "finding": "stale_map_sha",
                    "detail": f"bytes {digest} receipt {receipt['map_sha256']}",
                })
            receipt_ids = {step["id"] for step in receipt["steps"]}
            for step_id in sorted(map_ids - receipt_ids):
                findings.append({"finding": "coverage_missing", "detail": step_id})
            for step_id in sorted(receipt_ids - map_ids):
                findings.append({"finding": "coverage_extra", "detail": step_id})
        findings.sort(key=lambda item: (item["finding"], item["detail"]))
        code = 0 if not findings else 1
        body = {
            "schema_version": "capability-map-check/v1",
            "map_sha256": digest,
            "findings": findings,
            "result": "NO_REGRESSION" if code == 0 else "REGRESSION",
            "scope": CAPABILITY_SCOPE,
        }
        return code, canonical(body)
    except Exception as error:
        return 5, canonical({"result": "INPUT_ERROR", "reason": str(error)})
