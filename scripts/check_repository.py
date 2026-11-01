#!/usr/bin/env python3
"""Bootstrap checks only: this does not authenticate receipts or grade Bots."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    policy = json.loads((ROOT / "docs/standards/审查门槛.json").read_text())
    assert policy["standard_version"] == "TRUST-REVIEW-1.0", "review standard-version changes explicitly"
    assert policy["automation"]["automatic_stage_upgrade_ceiling"] == 2
    assert policy["automation"]["automatic_enter_stage3_or_4_allowed"] is False
    assert policy["qualified_business_pass"]["producer_equals_verifier_allowed"] is False
    assert policy["counting"]["finalized_missing_evidence_breaks_streak"] is True
    assert policy["qualified_business_pass"]["outer_inner_verdict_must_match"] is True
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
    print("PASS: repository structure and standard contracts; runtime trust review NOT_TESTED")


if __name__ == "__main__":
    main()
