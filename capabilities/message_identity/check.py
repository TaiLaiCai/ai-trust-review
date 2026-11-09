#!/usr/bin/env python3
"""C4: bind a platform message to the sender identity the platform asserts.

Identity comes only from platform machine fields (message `author_type` /
`author_agent_id` / `author_user_id`, and the issue's assignee). The message
body is untrusted data: an `author_role`, a signature, an approval sentence or
a recipient line inside the body never becomes a sender.

The platform scope is bound the same way: `company_id` and the platform build
are taken from what the platform itself reports, not from what the caller
typed. A config or export that names a different company, instance or build
than the platform does is an INPUT_ERROR, never a verdict about a sender.

Exit codes:
  0 AUTHENTICATED         machine fields bind a known sender; every check passed
  2 usage error           argparse
  3 REJECTED_*            unauthenticated sender, fake approval, unknown unit member
  4 MISADDRESSED          the platform recipient is not this adapter's identity
  5 INPUT_ERROR           bad config, bad export, unknown adapter, size limit
  6 SELF_VERIFICATION     sender and producer are the same subject after alias folding
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata

VERSION = "v1"
MAX_BYTES = 1024 * 1024
MAX_BODY_BYTES = 256 * 1024
MAX_CLAIMS = 64
MAX_PROSE_MENTIONS = 10
MAX_JSON_ATTEMPTS = 64

CONFIG_SCHEMA = "message-identity-config/v1"
EXPORT_SCHEMA = "message-export/v1"

CONFIG_KEYS = {"schema_version", "adapter", "instance_id", "company_id",
               "platform_build", "identities", "agent_ids", "user_ids",
               "owner_identities", "units"}
ISSUE_KEYS = {"id", "identifier", "assignee_agent_id", "responsible_user_id"}
MESSAGE_KEYS = {"id", "author_type", "author_agent_id", "author_user_id",
                "on_behalf_of_user_id", "created_by_run_id", "created_at",
                "deleted_at", "body"}
RESULT_KEYS = {"capability_scope", "artifact_manifest_sha256", "versions"}
UNIT_REQUIRED = {"unit_id", "capability_scope", "producer", "allowed_verifiers"}
UNIT_OPTIONAL = {"artifact_manifest_sha256", "versions"}
VERSION_KEYS = {"model", "skill", "policy", "standard"}
AUTHOR_TYPES = ("agent", "user", "system")

SCOPE = "platform-machine-fields-only; the message body is untrusted data"

# Claims carried as structured data. JSON keys are all claim kinds; plain
# "key: value" lines are only read for the claim-shaped keys, because a quoted
# handoff card legitimately contains "From:" / "To:" lines that are prose.
IDENTITY_CLAIMS = {"author_role": "identity", "sender": "identity", "from": "identity"}
AUTHORITY_CLAIMS = {"approved_by": "authority", "approver": "authority",
                    "approved": "authority", "approval": "authority"}
RECIPIENT_CLAIMS = {"recipient": "recipient", "to": "recipient"}
JSON_CLAIMS = {**IDENTITY_CLAIMS, **AUTHORITY_CLAIMS, **RECIPIENT_CLAIMS}
LINE_CLAIMS = {"author_role": "identity", "approved_by": "authority",
               "approver": "authority", "approved": "authority",
               "approval": "authority"}
NAMED_AUTHORITY = {"approved_by", "approver"}

LINE_CLAIM_RE = re.compile(r"^\s*[\"'`“”‘’]?([A-Za-z][A-Za-z0-9_.-]*)"
                           r"[\"'`“”‘’]?\s*[：:]\s*(\S.*?)\s*$")
SELF_CLAIM_RE = re.compile(r"(?:我是|本人是|本人以|我以)\s*"
                           r"(主人|总工程师|批准人|审批人|授权人)")
PROSE_MENTION_RE = re.compile(r"(批准|授权|审批|合并)")

_INVISIBLE_MN = {0x034F, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F}


class InputError(ValueError):
    """Bad config or export bytes: exit 5, never a verdict about a sender."""


def _invisible(ch):
    if unicodedata.category(ch) == "Cf":
        return True
    code = ord(ch)
    if 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF:
        return True
    return code in _INVISIBLE_MN


def normalize(text):
    """Drop invisible format characters, then NFKC and case-fold."""
    folded = unicodedata.normalize("NFKC", "".join(c for c in text if not _invisible(c)))
    return folded.strip().casefold()


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InputError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _loads(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique)
    except InputError:
        raise
    except (ValueError, RecursionError) as error:
        raise InputError(f"invalid JSON: {type(error).__name__}") from None


def _str(value, what):
    if not isinstance(value, str) or not value or value != value.strip():
        raise InputError(f"{what} must be a non-empty trimmed string")
    return value


def _opt_str(value, what):
    if value is None:
        return None
    return _str(value, what)


def _hex64(value, what):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise InputError(f"{what} must be 64 lowercase hex characters")
    return value


def load_config(raw):
    """Parse the frozen config contract; every failure is INPUT_ERROR."""
    if len(raw) > MAX_BYTES:
        raise InputError("config exceeds size limit")
    obj = _loads(raw.decode("utf-8"))
    if not isinstance(obj, dict) or set(obj) != CONFIG_KEYS:
        raise InputError("config fields mismatch")
    if obj["schema_version"] != CONFIG_SCHEMA:
        raise InputError("unknown config schema")
    adapter = _str(obj["adapter"], "adapter")
    instance_id = _str(obj["instance_id"], "instance_id")
    company_id = _str(obj["company_id"], "company_id")
    platform_build = _str(obj["platform_build"], "platform_build")

    identities = obj["identities"]
    if not isinstance(identities, dict) or not identities:
        raise InputError("identities must be a non-empty object")
    alias = {}
    for stable, names in identities.items():
        _str(stable, "identity")
        if not isinstance(names, list):
            raise InputError("identity aliases must be a list")
        for name in [stable] + names:
            _str(name, "alias")
            folded = normalize(name)
            if alias.get(folded, stable) != stable:
                raise InputError(f"ambiguous alias: {name}")
            alias[folded] = stable

    def known(name, what):
        _str(name, what)
        if name not in identities:
            raise InputError(f"{what} references unknown identity: {name}")
        return name

    platform_ids = {}
    for field in ("agent_ids", "user_ids"):
        table = obj[field]
        if not isinstance(table, dict):
            raise InputError(f"{field} must be an object")
        for platform_id, stable in table.items():
            _str(platform_id, f"{field} key")
            _str(stable, f"{field} value")
            known(stable, f"{field} value")
            if platform_id in platform_ids and platform_ids[platform_id] != stable:
                raise InputError(f"ambiguous platform id: {platform_id}")
            platform_ids[platform_id] = stable

    owners = obj["owner_identities"]
    if not isinstance(owners, list):
        raise InputError("owner_identities must be a list")
    owner_ids = {known(o, "owner_identities") for o in owners}

    units = obj["units"]
    if not isinstance(units, list) or not units:
        raise InputError("units must be a non-empty list")
    parsed_units = {}
    for unit in units:
        if not isinstance(unit, dict):
            raise InputError("each unit must be an object")
        keys = set(unit)
        if not UNIT_REQUIRED <= keys or not keys <= UNIT_REQUIRED | UNIT_OPTIONAL:
            raise InputError("unit fields mismatch")
        unit_id = _str(unit["unit_id"], "unit_id")
        if unit_id in parsed_units:
            raise InputError("duplicate unit_id")
        producer = known(unit["producer"], "unit producer")
        verifiers = unit["allowed_verifiers"]
        if not isinstance(verifiers, list):
            raise InputError("allowed_verifiers must be a list")
        verifier_ids = {known(v, "unit allowed_verifiers") for v in verifiers}
        if producer in verifier_ids:
            raise InputError("producer cannot be an allowed verifier")
        entry = {
            "unit_id": unit_id,
            "capability_scope": _str(unit["capability_scope"], "unit capability_scope"),
            "producer": producer,
            "allowed_verifiers": sorted(verifier_ids),
        }
        if "artifact_manifest_sha256" in unit and unit["artifact_manifest_sha256"] is not None:
            entry["artifact_manifest_sha256"] = _hex64(
                unit["artifact_manifest_sha256"], "unit artifact_manifest_sha256")
        if "versions" in unit and unit["versions"] is not None:
            versions = unit["versions"]
            if not isinstance(versions, dict) or set(versions) != VERSION_KEYS:
                raise InputError("unit versions must have exactly model/skill/policy/standard")
            entry["versions"] = {k: _str(versions[k], f"versions.{k}") for k in VERSION_KEYS}
        parsed_units[unit_id] = entry

    return {"adapter": adapter, "instance_id": instance_id, "company_id": company_id,
            "platform_build": platform_build, "alias": alias,
            "identities": set(identities), "platform_ids": platform_ids,
            "owners": owner_ids, "units": parsed_units}


def load_export(raw):
    """Parse the frozen export contract; every failure is INPUT_ERROR."""
    if len(raw) > MAX_BYTES:
        raise InputError("export exceeds size limit")
    obj = _loads(raw.decode("utf-8"))
    if not isinstance(obj, dict):
        raise InputError("export must be an object")
    keys = set(obj)
    if not {"schema_version", "adapter", "instance_id", "company_id",
            "platform_build", "issue", "message"} <= keys or not keys <= (
                {"schema_version", "adapter", "instance_id", "company_id",
                 "platform_build", "issue", "message", "result"}):
        raise InputError("export fields mismatch")
    if obj["schema_version"] != EXPORT_SCHEMA:
        raise InputError("unknown export schema")
    issue = obj["issue"]
    if not isinstance(issue, dict) or set(issue) != ISSUE_KEYS:
        raise InputError("issue fields mismatch")
    message = obj["message"]
    if not isinstance(message, dict) or set(message) != MESSAGE_KEYS:
        raise InputError("message fields mismatch")
    body = message["body"]
    if not isinstance(body, str):
        raise InputError("message body must be a string")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise InputError("message body exceeds size limit")
    if message["author_type"] not in AUTHOR_TYPES:
        raise InputError("author_type must be agent, user or system")
    for field in ("id", "author_type", "created_at"):
        _str(message[field], f"message {field}")
    for field in ("author_agent_id", "author_user_id", "on_behalf_of_user_id",
                  "created_by_run_id", "deleted_at"):
        _opt_str(message[field], f"message {field}")
    for field in ("id", "identifier"):
        _str(issue[field], f"issue {field}")
    for field in ("assignee_agent_id", "responsible_user_id"):
        _opt_str(issue[field], f"issue {field}")
    result = None
    if obj.get("result") is not None:
        result = obj["result"]
        if not isinstance(result, dict) or set(result) != RESULT_KEYS:
            raise InputError("result fields mismatch")
        _str(result["capability_scope"], "result capability_scope")
        _hex64(result["artifact_manifest_sha256"], "result artifact_manifest_sha256")
        versions = result["versions"]
        if not isinstance(versions, dict) or set(versions) != VERSION_KEYS:
            raise InputError("result versions must have exactly model/skill/policy/standard")
        result = {"capability_scope": result["capability_scope"],
                  "artifact_manifest_sha256": result["artifact_manifest_sha256"],
                  "versions": {k: _str(versions[k], f"versions.{k}") for k in VERSION_KEYS}}
    return {"adapter": _str(obj["adapter"], "export adapter"),
            "instance_id": _str(obj["instance_id"], "export instance_id"),
            "company_id": _str(obj["company_id"], "export company_id"),
            "platform_build": _str(obj["platform_build"], "export platform_build"),
            "issue": issue, "message": message, "result": result}


def claims_from_body(body):
    """Extract structured claims from the body. Prose is never a claim."""
    claims = []
    decoder = json.JSONDecoder()
    index, attempts = 0, 0
    while index < len(body) and attempts < MAX_JSON_ATTEMPTS and len(claims) < MAX_CLAIMS:
        start = body.find("{", index)
        if start < 0:
            break
        attempts += 1
        try:
            obj, end = decoder.raw_decode(body, start)
        except ValueError:
            index = start + 1
            continue
        index = end
        if not isinstance(obj, dict):
            continue
        for key, value in obj.items():
            kind = JSON_CLAIMS.get(str(key).strip().casefold())
            if kind and isinstance(value, (str, bool)):
                claims.append({"kind": kind, "key": str(key).strip().casefold(),
                               "value": value, "source": "json"})
    for line in body.splitlines():
        match = LINE_CLAIM_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip().casefold()
        kind = LINE_CLAIMS.get(key)
        if kind:
            claims.append({"kind": kind, "key": key, "value": match.group(2).strip(),
                           "source": "line"})
    for match in SELF_CLAIM_RE.finditer(body):
        claims.append({"kind": "authority", "key": "self_claim",
                       "value": match.group(1), "source": "self_claim"})
    return claims[:MAX_CLAIMS]


def prose_mentions(body):
    """Free-text approval wording. Recorded, never binding."""
    out = []
    for match in PROSE_MENTION_RE.finditer(body):
        start = max(0, match.start() - 12)
        out.append({"kind": "approval_mention", "text": body[start:match.end() + 12].strip(),
                    "effect": "no_effect"})
        if len(out) >= MAX_PROSE_MENTIONS:
            break
    return out


def _reject(verdict, reason, **extra):
    result = {"verdict": verdict, "reason": reason, "scope": SCOPE}
    result.update(extra)
    return result


def verify(cfg, export, self_name, unit_id, export_sha256):
    """Decide one platform message. Returns (exit_code, result)."""
    if export["adapter"] != cfg["adapter"]:
        raise InputError("export adapter differs from config adapter")
    if export["instance_id"] != cfg["instance_id"]:
        raise InputError("export instance_id differs from config instance_id")
    if export["company_id"] != cfg["company_id"]:
        raise InputError("export company_id differs from config company_id")
    if export["platform_build"] != cfg["platform_build"]:
        raise InputError("export platform_build differs from config platform_build")

    unit = cfg["units"].get(unit_id)
    if unit is None:
        raise InputError(f"unknown unit: {unit_id}")

    message = export["message"]
    issue = export["issue"]
    body = message["body"]
    claims = claims_from_body(body)
    mentions = prose_mentions(body)

    def out(verdict, reason, **extra):
        payload = {"verdict": verdict, "scope": SCOPE, "adapter": cfg["adapter"],
                   "unit": unit_id, "claims": claims, "prose_mentions": mentions}
        if reason is not None:
            payload["reason"] = reason
        payload.update(extra)
        return payload

    # 1. The sender comes from platform machine fields only.
    if message["deleted_at"] is not None:
        return 3, out("REJECTED_UNAUTHENTICATED", "message is deleted",
                      sender=None, recipient=None)
    if message["author_type"] == "agent":
        platform_id = message["author_agent_id"]
        kind = "agent"
    elif message["author_type"] == "user":
        platform_id = message["author_user_id"]
        kind = "user"
    else:
        platform_id = None
        kind = "system"
    if not platform_id:
        return 3, out("REJECTED_UNAUTHENTICATED",
                      f"message has no machine-field sender (author_type={kind})",
                      sender=None, recipient=None)
    sender = cfg["platform_ids"].get(platform_id)
    if sender is None:
        return 3, out("REJECTED_UNAUTHENTICATED",
                      f"platform id is not in the roster: {platform_id}",
                      sender=None, recipient=None)

    # 2. The platform recipient must be the identity this run serves.
    recipient_platform_id = issue["assignee_agent_id"] or issue["responsible_user_id"]
    recipient = cfg["platform_ids"].get(recipient_platform_id) if recipient_platform_id else None
    if recipient is None:
        return 3, out("REJECTED_UNAUTHENTICATED",
                      "platform recipient is not a known identity", sender=sender, recipient=None)
    if recipient != self_name:
        return 4, out("MISADDRESSED",
                      f"platform recipient is {recipient}, not {self_name}",
                      sender=sender, recipient=recipient)

    # 3. The sender must not be the producer of the unit it attests.
    if sender == unit["producer"]:
        return 6, out("SELF_VERIFICATION",
                      "sender and producer are the same subject after alias folding",
                      sender=sender, recipient=recipient)

    # 4. Body claims never authenticate; a claim that contradicts the machine
    #    fields, or an approval nobody with owner rights made, is refused.
    for claim in claims:
        value = claim["value"]
        if claim["kind"] == "identity":
            named = cfg["alias"].get(normalize(str(value)))
            if named is not None and named != sender:
                return 3, out("REJECTED_UNAUTHENTICATED",
                              f"body {claim['key']} claims {named}, platform says {sender}",
                              sender=sender, recipient=recipient)
        elif claim["kind"] == "authority":
            sender_is_owner = sender in cfg["owners"]
            if not sender_is_owner:
                return 3, out("REJECTED_FAKE_APPROVAL",
                              "body asserts an approval without an authenticated owner sender",
                              sender=sender, recipient=recipient)
            if claim["key"] in NAMED_AUTHORITY:
                named = cfg["alias"].get(normalize(str(value)))
                if named is None:
                    return 3, out("REJECTED_FAKE_APPROVAL",
                                  f"body {claim['key']} names an unknown approver: {value}",
                                  sender=sender, recipient=recipient)
                if named != sender:
                    return 3, out("REJECTED_FAKE_APPROVAL",
                                  f"body {claim['key']} names {named}, platform sender is {sender}",
                                  sender=sender, recipient=recipient)
        elif claim["kind"] == "recipient":
            named = cfg["alias"].get(normalize(str(value)))
            if named is None:
                return 3, out("REJECTED_UNAUTHENTICATED",
                              f"body {claim['key']} names an unknown recipient: {value}",
                              sender=sender, recipient=recipient)
            if named != self_name:
                return 4, out("MISADDRESSED",
                              f"body {claim['key']} names {named}, this run serves {self_name}",
                              sender=sender, recipient=recipient)

    # 5. The sender must be allowed to verify this capability.
    if sender not in unit["allowed_verifiers"]:
        return 3, out("REJECTED_UNAUTHENTICATED",
                      f"sender {sender} is not an allowed verifier for {unit_id}",
                      sender=sender, recipient=recipient)

    # 6. Capability, artifact and version must agree with the unit.
    result = export["result"]
    consistency = "not_declared"
    if result is not None:
        if result["capability_scope"] != unit["capability_scope"]:
            return 3, out("REJECTED_UNAUTHENTICATED",
                          f"capability_scope {result['capability_scope']} differs from unit "
                          f"{unit['capability_scope']}", sender=sender, recipient=recipient)
        expected_sha = unit.get("artifact_manifest_sha256")
        if expected_sha is not None and expected_sha != result["artifact_manifest_sha256"]:
            return 3, out("REJECTED_UNAUTHENTICATED",
                          "artifact_manifest_sha256 differs from the unit",
                          sender=sender, recipient=recipient)
        expected_versions = unit.get("versions")
        if expected_versions is not None and expected_versions != result["versions"]:
            return 3, out("REJECTED_UNAUTHENTICATED",
                          "versions differ from the unit", sender=sender, recipient=recipient)
        consistency = "declared-and-matched"

    evidence_ref = (f"{cfg['adapter']}://{cfg['instance_id']}/{cfg['company_id']}"
                    f"/issues/{issue['id']}/comments/{message['id']}")
    return 0, out("AUTHENTICATED", None,
                  sender=sender, sender_kind=kind, sender_platform_id=platform_id,
                  recipient=recipient, recipient_platform_id=recipient_platform_id,
                  on_behalf_of=message["on_behalf_of_user_id"],
                  capability_scope=unit["capability_scope"],
                  consistency=consistency,
                  evidence_ref=evidence_ref, evidence_sha256=export_sha256,
                  attestation={"adapter": cfg["adapter"], "sender": sender,
                               "evidence_ref": evidence_ref})


def self_fingerprint():
    with open(__file__, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return f"{VERSION} {digest}"


def _read(path):
    if path == "-":
        return sys.stdin.buffer.read(MAX_BYTES + 1)
    with open(path, "rb") as handle:
        return handle.read(MAX_BYTES + 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="store_true",
                        help="print version and full sha256 of this file, then exit 0")
    subs = parser.add_subparsers(dest="cmd")
    for name, help_text in (("verify", "verify a platform message and print the verdict"),
                             ("attest", "print only the gate-compatible attestation")):
        sub = subs.add_parser(name, help=help_text)
        sub.add_argument("--config", required=True, help="identity config JSON")
        sub.add_argument("--export", required=True, help="platform message export JSON")
        sub.add_argument("--self", required=True, dest="me", help="identity this run serves")
        sub.add_argument("--unit", required=True, help="unit_id being attested")
    args = parser.parse_args(argv)
    if args.version:
        print(self_fingerprint())
        return 0
    if not args.cmd:
        parser.print_help()
        return 2
    try:
        cfg = load_config(_read(args.config))
        raw = _read(args.export)
        if len(raw) > MAX_BYTES:
            raise InputError("export exceeds size limit")
        export = load_export(raw)
        export_sha = hashlib.sha256(raw).hexdigest()
        me = cfg["alias"].get(normalize(args.me))
        if me is None:
            raise InputError(f"--self {args.me!r} is not a known identity")
        code, result = verify(cfg, export, me, args.unit, export_sha)
    except InputError as error:
        code, result = 5, {"verdict": "INPUT_ERROR", "reason": str(error), "scope": SCOPE}
    except UnicodeDecodeError:
        code, result = 5, {"verdict": "INPUT_ERROR", "reason": "input is not UTF-8",
                           "scope": SCOPE}
    except OSError:
        code, result = 5, {"verdict": "INPUT_ERROR", "reason": "unreadable input file",
                           "scope": SCOPE}
    if args.cmd == "attest":
        if code == 0:
            print(json.dumps(result["attestation"], ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
