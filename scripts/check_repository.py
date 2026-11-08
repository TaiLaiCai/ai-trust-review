#!/usr/bin/env python3
"""Bootstrap checks only: this does not authenticate receipts or grade Bots."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The five capability maps. control/gate already uses the same three keys and is not one of them.
CAPABILITY_FEATURE_MAPS = (
    "capabilities/evidence_package/feature-map.json",
    "capabilities/handoff_conventions/feature-map.json",
    "capabilities/handoff_recipient/feature-map.json",
    "capabilities/rerun_receipt/feature-map.json",
    "capabilities/review_readonly/feature-map.json",
)
REVIEW_READONLY_SCOPE = (
    "two-observation declared file or tree bytes only; not OS enforcement or stage grading"
)


def require_unverified_independent_verification(block, label):
    """Schema only. No receipt is invented: the triple stays NOT_TESTED/null/null."""
    assert isinstance(block, dict), f"{label}: independent_verification must be an object"
    assert list(block) == ["status", "verifier", "head_sha"], (
        f"{label}: independent_verification keys must be status, verifier, head_sha"
    )
    assert block["status"] == "NOT_TESTED", (
        f"{label}: unverified status must stay NOT_TESTED, not {block['status']!r}"
    )
    assert block["verifier"] is None and block["head_sha"] is None, (
        f"{label}: unverified verifier and head_sha must stay null"
    )


def check_capability_feature_maps(root=ROOT):
    found = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "capabilities").glob("*/feature-map.json")
    )
    assert found == list(CAPABILITY_FEATURE_MAPS), f"capability feature maps changed: {found}"
    for rel in found:
        data = json.loads((root / rel).read_text())
        assert "independent_verification" in data, f"{rel}: missing independent_verification"
        require_unverified_independent_verification(data["independent_verification"], rel)
    review = json.loads((root / "capabilities/review_readonly/feature-map.json").read_text())
    assert review["runtime_bot_integration"] == "NOT_TESTED"
    assert review["independent_acceptance"] == "NOT_TESTED"
    assert review["scope"] == REVIEW_READONLY_SCOPE


def main():
    policy = json.loads((ROOT / "docs/standards/审查门槛.json").read_text())
    assert policy["standard_version"] == "TRUST-REVIEW-1.0", "review standard-version changes explicitly"
    assert policy["automation"]["automatic_stage_upgrade_ceiling"] == 2
    assert policy["automation"]["automatic_enter_stage3_or_4_allowed"] is False
    assert policy["qualified_business_pass"]["producer_equals_verifier_allowed"] is False
    assert policy["counting"]["finalized_missing_evidence_breaks_streak"] is True
    assert policy["qualified_business_pass"]["outer_inner_verdict_must_match"] is True
    assert policy["automation"]["min_M2_healthy_ci_days"] == 7
    assert policy["stages"]["3"]["min_shadow_days"] == 14
    assert policy["stages"]["4"]["min_healthy_ci_days"] == 30
    standards = ROOT / "docs/standards"
    text06 = (standards / "06-Dune与CI上线门禁.md").read_text()
    text00 = (standards / "00-入口与统一判定.md").read_text()
    text02 = (standards / "02-阶段2-自证正确.md").read_text()
    text03 = (standards / "03-阶段3-接收信号.md").read_text()
    assert "M2要求连续7个自然日" in text06
    assert "M2要求连续14个自然日" not in text06
    assert "检测器审阅、7天CI、持久触发实测" in text06
    assert "flaky测试14天内翻转≥2次" in text06
    assert "阶段3另有14天/100真实信号的影子窗口" in text06
    assert "M2：CI 连续 7 天全绿" in text00
    assert "阶段 3：14 天、100 个真实影子信号" in text00
    assert "CI连续7天" in text02
    assert "连续14个自然日" in text03
    manifest = json.loads((standards / "source-manifest.json").read_text())
    assert manifest["original_source_sha256"]["06-Dune与CI上线门禁.md"] == (
        "53c46caa23555f96f0cf3ca8c23ee290574c308c266d3503d4de6570c28772ec"
    )
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "M2 窗口：连续 7 个自然日" in workflow
    assert "cron: '0 3 * * *'" in workflow
    assert "连续 14 个自然日" not in workflow
    for stage, spec in policy["stages"].items():
        text = (ROOT / "docs/standards" / spec["file"]).read_text()
        ids = re.findall(r"^\| (S\d-\d\d) \|", text, re.MULTILINE)
        assert ids == spec["gates"], f"stage {stage}: gate IDs differ"
        assert len(ids) == 8 and len(set(ids)) == 8
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        text = path.read_text()
        assert not re.search(r"^\d+\|", text, re.MULTILINE), f"{path}: copied reader line numbers"
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#")[0]
            assert (path.parent / target).is_file(), f"{path}: missing {target}"
    check_capability_feature_maps()
    print("PASS: repository structure and standard contracts; runtime trust review NOT_TESTED")


if __name__ == "__main__":
    main()
