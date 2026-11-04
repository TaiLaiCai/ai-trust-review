#!/usr/bin/env python3
"""Pre-start check for a handoff: is it addressed to me, and is it complete?

Reads handoff text as data (never executes anything in it) and prints one JSON
object. Exit codes: 0 ACCEPT, 3 INCOMPLETE/AMBIGUOUS, 4 MISADDRESSED,
5 input/config error, 2 usage error (argparse).
"""
import argparse
import json
import re
import sys
import unicodedata

REQUIRED = ("目标", "输入", "约束", "验收标准", "交付")
LABELS = ("From", "To") + REQUIRED + ("待确认", "附注")
MAX_BYTES = 256 * 1024
_LABEL = "|".join(re.escape(x) for x in sorted(LABELS, key=len, reverse=True))
_BOUNDARY = "".join(f"(?<={re.escape(c)})|" for c in "】。；;，,）)：:")
FIELD = re.compile(rf"(?:^|(?<=\s)|{_BOUNDARY[:-1]})({_LABEL})\s*[：:]", re.MULTILINE | re.IGNORECASE)
_BOUNDARY_CHARS = set("】。；;，,）)：:")


def label_has_combining_mark(text):
    """Known field label with a nonspacing mark inserted before its colon."""
    n = len(text)
    for i in range(n):
        if i and not (text[i - 1].isspace() or text[i - 1] in _BOUNDARY_CHARS):
            continue
        for label in LABELS:
            j, saw, matched = i, False, True
            for ch in label:
                while j < n and unicodedata.category(text[j]) == "Mn":
                    saw = True
                    j += 1
                if j >= n or text[j].casefold() != ch.casefold():
                    matched = False
                    break
                j += 1
            if not matched:
                continue
            while j < n and unicodedata.category(text[j]) == "Mn":
                saw = True
                j += 1
            k = j
            while k < n and text[k] in " \t":
                k += 1
            if saw and k < n and text[k] in "：:":
                return True
    return False


class InputError(ValueError):
    pass


# Mn marks that Unicode treats as default-ignorable or as variation selectors.
# Visible diacritics (for example U+0301) are not in this set: they stay in
# prose and names, and a field label that still contains one is AMBIGUOUS.
_INVISIBLE_MN = {0x034F, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F}


def invisible(ch):
    if unicodedata.category(ch) == "Cf":
        return True
    o = ord(ch)
    if 0xFE00 <= o <= 0xFE0F or 0xE0100 <= o <= 0xE01EF:
        return True
    return o in _INVISIBLE_MN


def strip_invisible(text):
    return "".join(ch for ch in text if not invisible(ch))


def normalize(text):
    """Drop Cf and invisible Mn (CGJ, variation selectors), then NFKC.

    A second To hidden by U+034F or U+FE0F is therefore visible to the label
    scan. Visible combining marks are not deleted globally.
    """
    return unicodedata.normalize("NFKC", strip_invisible(text))


def unique_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InputError("duplicate aliases JSON key")
        out[key] = value
    return out


def load_aliases(raw):
    try:
        data = json.loads(raw, object_pairs_hook=unique_keys)
    except InputError:
        raise
    except ValueError:
        raise InputError("aliases file is not valid JSON") from None
    if not isinstance(data, dict) or not data:
        raise InputError("aliases must be a non-empty object {stable_id: [alias, ...]}")
    table = {}
    for stable, names in data.items():
        if not isinstance(stable, str) or not stable.strip() or not isinstance(names, list):
            raise InputError("each identity needs a name and a list of aliases")
        for name in [stable] + names:
            if not isinstance(name, str) or not name.strip():
                raise InputError("aliases must be non-empty strings")
            key = normalize(name).strip().casefold()
            if table.get(key, stable) != stable:
                raise InputError(f"ambiguous alias: {name}")
            table[key] = stable
    return table


def fields(text):
    """Return {label: [values...]} for header-style fields in the text."""
    found = {}
    marks = list(FIELD.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        value = text[m.end():end].strip()
        label = {"to": "To", "from": "From"}.get(m.group(1).casefold(), m.group(1))
        found.setdefault(label, []).append(value)
    return found


TRAILING_NOTE = re.compile(r"\s*[（(][^（）()]*[）)]\s*$")


def first_line(value):
    """Recipient name: first line, minus a trailing (note) and punctuation."""
    line = value.splitlines()[0].strip() if value else ""
    line = line.rstrip("。.，,;；、 ")
    while TRAILING_NOTE.search(line):
        line = TRAILING_NOTE.sub("", line).rstrip("。.，,;；、 ")
    return line


def check(text, me, aliases):
    who = aliases.get(normalize(me).strip().casefold())
    if who is None:
        raise InputError(f"--self {me!r} is not in the alias table")
    stripped = strip_invisible(text)
    if label_has_combining_mark(stripped):
        return 3, {"verdict": "AMBIGUOUS", "reason": "combining mark in field label",
                   "next": "不执行；字段名含组合附加符号，请发件人去掉后重发"}
    got = fields(unicodedata.normalize("NFKC", stripped))
    if any(len([line for line in v.splitlines() if line.strip()]) != 1
           for v in got.get("To", [])):
        return 3, {"verdict": "AMBIGUOUS", "reason": "empty or multiline recipient",
                   "next": "不执行；每个 To 必须只有一个非空收件人行，请发件人澄清"}
    recipients = {first_line(v) for v in got.get("To", []) if first_line(v)}
    if not recipients:
        return 3, {"verdict": "INCOMPLETE", "reason": "no To field",
                   "next": "不执行；请发件人补上收件人"}
    resolved = {r: aliases.get(r.casefold()) for r in recipients}
    unknown = sorted(r for r, s in resolved.items() if s is None)
    if unknown:
        return 3, {"verdict": "AMBIGUOUS", "reason": "unknown recipient", "to": unknown,
                   "next": "不执行；向发件人确认收件人"}
    targets = set(resolved.values())
    if len(targets) > 1:
        return 3, {"verdict": "AMBIGUOUS", "reason": "multiple recipients", "to": sorted(targets),
                   "next": "不执行；一张交接单只能有一个收件人"}
    target = targets.pop()
    if target != who:
        return 4, {"verdict": "MISADDRESSED", "self": who, "to": target,
                   "next": "不执行、不转派；回问发件人。看板指派不能替代正文收件人"}
    missing = [f for f in REQUIRED if not any(v.strip() for v in got.get(f, []))]
    if missing:
        return 3, {"verdict": "INCOMPLETE", "self": who, "missing": missing,
                   "next": "不执行；复述缺口，等完整交接单"}
    return 0, {"verdict": "ACCEPT", "self": who, "to": target,
               "scope": "recipient-and-fields-only; does not validate content, approval or authority"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self", dest="me", required=True, help="identity of the bot about to start")
    p.add_argument("--aliases", required=True, help="JSON {stable_id: [alias, ...]}")
    p.add_argument("handoff", nargs="?", default="-", help="handoff text file, or - for stdin")
    args = p.parse_args(argv)
    try:
        with open(args.aliases, "rb") as f:
            aliases = load_aliases(f.read(MAX_BYTES + 1).decode("utf-8"))
        if args.handoff == "-":
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            with open(args.handoff, "rb") as f:
                raw = f.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InputError("handoff exceeds 256 KiB")
        code, result = check(raw.decode("utf-8"), args.me, aliases)
    except (InputError, UnicodeDecodeError) as error:
        code, result = 5, {"verdict": "INPUT_ERROR", "reason": str(error)}
    except OSError:
        code, result = 5, {"verdict": "INPUT_ERROR", "reason": "unreadable file"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
