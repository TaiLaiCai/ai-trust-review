#!/usr/bin/env python3
"""Check the three addendum boundaries. Does not print restricted input text."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORED_SAMPLE = "79e0d15f5a5729b4fe8afb1b7376d8352d7f4ca08b8534c40faa4d47827df099"
REGISTERED_SAMPLE = "094e5186e657456fdf58c4198b07949237c9370128d6224b9aa165dd6963ac16"
REGISTERED_STATUS = "49a428cca57668bcfae5dececca9aeec3caacb40c7bf519d128890fc7b708549"
FORBIDDEN_SHA = "d4cd93763e08981c81617ae480b5c118ff32d53204d8de92bfdbabc07180703a"
FORBIDDEN_CHARS = 24
SAFE_FLAG = (
    "未入本候选。registered_value 只引用历史登记 SHA,不是本树实测。"
    "notes 正文不收录,不生成替代文件。"
    "历史提交仍可能保留旧正文;本候选不改写 git 历史,历史暴露未解决。"
)

results = []


def add(item, status, detail):
    results.append((item, status, detail))
    print(f"{item} {status} {detail}")


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contains_forbidden(text):
    if len(text) < FORBIDDEN_CHARS:
        return False
    for index in range(len(text) - FORBIDDEN_CHARS + 1):
        chunk = text[index:index + FORBIDDEN_CHARS].encode()
        if hashlib.sha256(chunk).hexdigest() == FORBIDDEN_SHA:
            return True
    return False


def main():
    merge = json.loads((ROOT / "merge-manifest.json").read_text())
    replay = json.loads((ROOT / "replay-kit-manifest.json").read_text())
    readme = (ROOT / "README.md").read_text()
    sample_path = ROOT / "replay-kit" / "sample_fixed.json"
    sample_bytes = sample_path.read_bytes()
    sample_sha = hashlib.sha256(sample_bytes).hexdigest()
    sample_entry = next(
        item for item in merge["entries"] if item["merge_path"] == "replay-kit/sample_fixed.json"
    )
    status_entry = next(
        item for item in merge["entries"] if item["merge_path"] == "replay-kit/status_input.json"
    )
    replay_entry = next(
        item for item in merge["entries"] if item["merge_path"] == "replay-kit-manifest.json"
    )
    sample_file = replay["files"][2]
    status_file = replay["files"][4]

    stored_ok = (
        sample_sha == STORED_SAMPLE
        and sample_entry["sha256"] == STORED_SAMPLE
        and sample_file["sha256_stored"] == STORED_SAMPLE
        and sample_file["sha256_exported"] == STORED_SAMPLE
        and sample_entry["source_sha256"] == REGISTERED_SAMPLE
        and sample_file["registered_value"] == REGISTERED_SAMPLE
        and sample_sha != REGISTERED_SAMPLE
        and sample_file["match"] is False
        and "不是路径脱敏" in sample_entry["note"]
        and "逐字节同源" not in sample_entry["note"]
        and "去私有路径" not in sample_entry["note"]
        and "不是路径脱敏" in sample_file["byte_relation"]
    )
    add("ITEM1_STORED_VS_REGISTERED", "PASS" if stored_ok else "FAIL",
        f"stored={sample_sha} registered={REGISTERED_SAMPLE}")

    parsed = json.loads(sample_bytes)
    derived = (json.dumps(parsed, ensure_ascii=False, separators=(", ", ": ")) + "\n").encode()
    derived_sha = hashlib.sha256(derived).hexdigest()
    derived_ok = derived_sha == REGISTERED_SAMPLE and derived != sample_bytes
    add("ITEM1_UNWRITTEN_RESERIALIZATION", "PASS" if derived_ok else "FAIL",
        f"sha={derived_sha} written_back=false")
    add("ITEM1_HISTORICAL_SOURCE_FILE", "NOT_TESTED", "source bytes are not in this tree")

    hash_ok = True
    checked = 0
    for entry in merge["entries"]:
        path = ROOT / entry["merge_path"]
        if entry["merge_path"] == "merge-manifest.json":
            hash_ok = False
        if path.is_file():
            checked += 1
            if sha256_file(path) != entry["sha256"]:
                hash_ok = False
                add("ITEM1_ENTRY_HASH", "FAIL", entry["merge_path"])
        elif entry["sha256"] is not None:
            hash_ok = False
            add("ITEM1_ABSENT_HASH_FILLED", "FAIL", entry["merge_path"])
    self_excluded = all(entry["merge_path"] != "merge-manifest.json" for entry in merge["entries"])
    replay_hash = sha256_file(ROOT / "replay-kit-manifest.json")
    scope_ok = (
        hash_ok
        and self_excluded
        and replay_entry["sha256"] == replay_hash
        and "避免清单自引用循环" in merge["hash_scope"]
        and "check_addendum_boundaries.py" in merge["hash_scope"]
    )
    add("ITEM1_STORED_HASHES_AND_SCOPE", "PASS" if scope_ok else "FAIL",
        f"checked={checked} replay_manifest={replay_hash}")

    forbidden_hits = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file():
            if contains_forbidden(path.read_text(errors="replace")):
                forbidden_hits.append(path.relative_to(ROOT).as_posix())
    flag_ok = (
        status_file["file"] == "status_input.json"
        and status_file["flag"] == SAFE_FLAG
        and "『" not in status_file["flag"]
        and "』" not in status_file["flag"]
        and not forbidden_hits
    )
    add("ITEM2_RESTRICTED_BODY_ABSENT", "PASS" if flag_ok else "FAIL",
        "hits=" + ",".join(forbidden_hits) if forbidden_hits else "current tree clear")
    add("ITEM2_HISTORY_PURGE", "NOT_TESTED",
        "git history is not rewritten; historical exposure remains open")

    boundary = replay["public_rerun_boundary"]["blocked_without_status_input"]
    readme_ok = (
        "79e0d15f5a5729b4fe8afb1b7376d8352d7f4ca08b8534c40faa4d47827df099" in readme
        and "094e5186e657456fdf58c4198b07949237c9370128d6224b9aa165dd6963ac16" in readme
        and "不是路径脱敏" in readme
        and "--file status_input.json" in readme
        and "stdin" in readme
        and "历史暴露范围未解决" in readme
        and "16/16 REPRODUCED" not in readme
        and "字节与 11-02 历史登记一致" not in readme
        and "Hark 已按包复跑" not in readme
    )
    manifest_ok = (
        not (ROOT / "replay-kit" / "status_input.json").exists()
        and status_entry["sha256"] is None
        and status_entry["status"] == "未入"
        and status_entry["source_sha256"] == REGISTERED_STATUS
        and status_file["sha256_stored"] is None
        and status_file["stored_in_this_candidate"] is False
        and "T2" in boundary
        and "--file status_input.json" in boundary["T2"]
        and "stdin" in boundary["T3"]
        and "不能顶替" in boundary["T3"]
        and "不是本候选的验证结果" in replay["replayability_conclusion"]["可重放"]
        and readme_ok
    )
    add("ITEM3_PUBLIC_BOUNDARY", "PASS" if manifest_ok else "FAIL",
        "status_input absent; T2/T3 impact stated")
    add("ITEM3_PRIVATE_8_OF_8", "NOT_TESTED",
        "historical private claim was not rerun and is not a verification")
    add("ITEM3_A2_PRIVATE_ORIGINALS", "NOT_TESTED",
        "stored A2 hashes can be recalculated; private originals are absent")

    failed = [item for item, status, _ in results if status == "FAIL"]
    print("OVERALL", "FAIL" if failed else "PASS", "failed=" + ",".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
