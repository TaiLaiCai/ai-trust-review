"""Correction-index columns and markdown registry tables.

Pure functions: no clock, no network, no filesystem. The caller supplies the
test-registration bytes. Exit 0 means this call found no column or test-name
finding. It does not mean a correction was red then green, and it does not
mean a loop is closed.

old_impl_red_green is always NOT_TESTED. This module does not run an old
implementation and does not invent that result.
"""
import importlib.util
import re
from datetime import datetime
from pathlib import Path

TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?[+-]\d\d:\d\d")
HEX = re.compile(r"[0-9a-f]{64}")
ENTRY_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
TAG = re.compile(r"<[^>\n]*>")
HIDE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|(?:^|\s)hidden(?:\s|=|$)", re.IGNORECASE)
REQUIRED_COLUMNS = (
    "id",
    "closed",
    "fix_kind",
    "test_registration",
    "old_impl_sha256",
    "new_impl_sha256",
    "registered_by",
    "closed_at",
)
ENTRY_KEYS = set(REQUIRED_COLUMNS)
INDEX_SCOPE = (
    "correction index columns and caller-supplied test bytes only; "
    "old-implementation red/green is NOT_TESTED; file existence on a real "
    "tree and CI execution are not checked here; exit 0 is not loop closure "
    "and not a stage change"
)
TABLE_SCOPE = (
    "registry column structure only; a hidden column is a finding; "
    "exit 0 is not loop closure and not a stage change"
)


def _load_map():
    path = Path(__file__).resolve().with_name("map_coverage.py")
    spec = importlib.util.spec_from_file_location("loop_closure_map_for_registry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MAP = _load_map()
InputError = _MAP.InputError
normalize_name = _MAP.normalize_name
load_json = _MAP.load_json
canonical = _MAP.canonical


def timestamp(value):
    """The one timestamp parser from issue #22: YYYY-MM-DDTHH:MM[:SS]±HH:MM."""
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise InputError("invalid timestamp format")
    try:
        offset = value[-6:]
        if int(offset[1:3]) > 23 or int(offset[4:]) > 59:
            raise ValueError("offset")
        return datetime.fromisoformat(value)
    except ValueError:
        raise InputError("invalid calendar time or offset") from None


def registrations_of(value):
    if not isinstance(value, dict) or any(
            not isinstance(key, str) or not isinstance(blob, bytes) for key, blob in value.items()):
        raise InputError("registrations must map test id to source bytes")
    return value


def visible_text(raw):
    return TAG.sub("", COMMENT.sub("", raw))


def concealed(raw):
    if COMMENT.search(raw) or HIDE.search(raw):
        return True
    return bool(raw.strip()) and not normalize_name(visible_text(raw))


def concealed_label(raw):
    inners = [match[4:-3] for match in COMMENT.findall(raw)]
    label = normalize_name(visible_text(raw)) or normalize_name(" ".join(inners))
    return label or "unnamed"


def check_registration(value, registrations, findings, where):
    text = value.strip() if isinstance(value, str) else ""
    if "::" not in text or not normalize_name(text):
        findings.append({"finding": "empty_test_name", "detail": where})
        return
    path, _, name = text.partition("::")
    if not path or not normalize_name(name):
        findings.append({"finding": "empty_test_name", "detail": where})
        return
    blob = registrations.get(text)
    if not isinstance(blob, bytes) or f"def {name}(".encode() not in blob:
        findings.append({"finding": "missing_test_name", "detail": text})


def finish(schema, findings, scope, extra):
    findings.sort(key=lambda item: (item["finding"], item["detail"]))
    code = 0 if not findings else 1
    body = {
        "schema_version": schema,
        "findings": findings,
        "result": "NO_REGRESSION" if code == 0 else "REGRESSION",
        "scope": scope,
    }
    body.update(extra)
    return code, canonical(body)


def assess_index(index_raw, registrations):
    """Return (exit_code, canonical_json_bytes). 0 / 1 / 5. Never a red/green PASS."""
    try:
        document = load_json(index_raw, "index")
        known = registrations_of(registrations)
        if not isinstance(document, dict) or set(document) != {"schema_version", "entries"}:
            raise InputError("index fields mismatch")
        if document["schema_version"] != "correction-index/v1":
            raise InputError("unsupported index schema_version")
        entries = document["entries"]
        if not isinstance(entries, list):
            raise InputError("entries must be a list")
        findings, listed, seen, previous = [], [], set(), None
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
                raise InputError("entry fields mismatch")
            if not isinstance(entry["id"], str) or not ENTRY_ID.fullmatch(entry["id"]):
                raise InputError("invalid correction id")
            if entry["id"] in seen:
                raise InputError("duplicate correction id")
            seen.add(entry["id"])
            if type(entry["closed"]) is not bool:
                raise InputError("closed must be a boolean")
            if entry["fix_kind"] not in {"hard", "soft"}:
                raise InputError("fix_kind must be hard or soft")
            if not isinstance(entry["test_registration"], str):
                raise InputError("invalid test_registration")
            for key in ("old_impl_sha256", "new_impl_sha256"):
                if not isinstance(entry[key], str) or not HEX.fullmatch(entry[key]):
                    raise InputError(f"invalid {key}")
            if not isinstance(entry["registered_by"], str) or not normalize_name(entry["registered_by"]):
                raise InputError("invalid registered_by")
            moment = timestamp(entry["closed_at"])
            if previous is not None and moment <= previous:
                raise InputError("correction timestamps not strictly increasing")
            previous = moment
            if entry["old_impl_sha256"] == entry["new_impl_sha256"]:
                findings.append({"finding": "impl_sha_not_distinct", "detail": entry["id"]})
            check_registration(entry["test_registration"], known, findings, entry["id"])
            listed.append({"id": entry["id"], "closed": entry["closed"], "fix_kind": entry["fix_kind"]})
        listed.sort(key=lambda item: item["id"])
        return finish(
            "correction-index-check/v1",
            findings,
            INDEX_SCOPE,
            {"entries": listed, "old_impl_red_green": "NOT_TESTED"},
        )
    except Exception as error:
        return 5, canonical({
            "result": "INPUT_ERROR",
            "reason": str(error),
            "old_impl_red_green": "NOT_TESTED",
        })


def row_cells(line):
    text = line.strip()
    if not text.startswith("|") or not text.endswith("|"):
        raise InputError("registry row must start and end with |")
    return [part.strip() for part in text[1:-1].split("|")]


def separator(cells):
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def assess_registry_table(table_text, registrations):
    """Return (exit_code, canonical_json_bytes). Hidden or missing columns are exit 1."""
    try:
        known = registrations_of(registrations)
        if not isinstance(table_text, str) or not table_text.strip():
            raise InputError("registry table is empty")
        lines = [line.strip() for line in table_text.splitlines() if line.strip()]
        parsed = [row_cells(line) for line in lines]
        if len(parsed) < 2 or not separator(parsed[1]) or separator(parsed[0]):
            raise InputError("registry table needs a header and a separator")
        if any(separator(row) for row in parsed[2:]):
            raise InputError("registry table has more than one header")
        header, rows = parsed[0], parsed[2:]
        if len(parsed[1]) != len(header):
            raise InputError("separator width mismatch")
        findings = []
        visible = []
        for raw in header:
            if concealed(raw):
                findings.append({"finding": "hidden_table_column", "detail": concealed_label(raw)})
                visible.append("")
            else:
                visible.append(normalize_name(visible_text(raw)))
        if visible != list(REQUIRED_COLUMNS):
            findings.append({
                "finding": "registry_columns_mismatch",
                "detail": " ".join(name or "?" for name in visible),
            })
        test_at = visible.index("test_registration") if "test_registration" in visible else None
        columns = {name: index for index, name in enumerate(visible) if name}
        for number, row in enumerate(rows, 1):
            if len(row) != len(header):
                raise InputError("registry row width mismatch")
            for index, raw in enumerate(row):
                if concealed(raw):
                    label = visible[index] or concealed_label(header[index])
                    findings.append({
                        "finding": "hidden_table_column",
                        "detail": f"row {number} {label}",
                    })
            if test_at is not None and not concealed(row[test_at]):
                check_registration(visible_text(row[test_at]), known, findings, f"row {number}")
            if visible == list(REQUIRED_COLUMNS):
                if not ENTRY_ID.fullmatch(visible_text(row[columns["id"]]).strip()):
                    raise InputError("invalid registry id")
                if visible_text(row[columns["closed"]]).strip() not in {"true", "false"}:
                    raise InputError("invalid closed cell")
                if visible_text(row[columns["fix_kind"]]).strip() not in {"hard", "soft"}:
                    raise InputError("invalid fix_kind cell")
                old = visible_text(row[columns["old_impl_sha256"]]).strip()
                new = visible_text(row[columns["new_impl_sha256"]]).strip()
                if not HEX.fullmatch(old) or not HEX.fullmatch(new):
                    raise InputError("invalid impl sha256")
                if old == new:
                    findings.append({"finding": "impl_sha_not_distinct", "detail": f"row {number}"})
                if not normalize_name(visible_text(row[columns["registered_by"]])):
                    raise InputError("invalid registered_by")
                timestamp(visible_text(row[columns["closed_at"]]).strip())
        return finish("registry-table/v1", findings, TABLE_SCOPE, {"columns": [name for name in visible if name]})
    except Exception as error:
        return 5, canonical({"result": "INPUT_ERROR", "reason": str(error)})
