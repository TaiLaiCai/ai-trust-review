import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("detect", ROOT / "detect.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

HEAD = "a" * 40
OTHER_HEAD = "b" * 40


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode()


def step(sid="s1", exit_code=0, citations=None, path="a.txt", line=1, excerpt="hello", command=("true",)):
    if citations is None:
        citations = ((path, line, excerpt),)
    return {"id": sid, "command": list(command), "exit_code": exit_code,
            "output_sha256": hashlib.sha256(b"ok\n").hexdigest(),
            "citations": [{"path": p, "line": l, "excerpt": e} for p, l, e in citations]}


def report(steps=None, loops=("L1",), head=HEAD, verifier="验收方", status="closed"):
    return {"schema_version": "loop-closure/v1", "head_sha": head,
            "producer": "生产方", "verifier": verifier, "status": status,
            "loops": list(loops), "steps": [] if steps is None else list(steps)}


def run(rep, files=None, outputs=None, expected=HEAD, previous=()):
    return d.assess(encode(rep), files if files is not None else {"a.txt": b"hello\n"},
                    outputs if outputs is not None else {"s1": b"ok\n"}, expected, list(previous))


def findings(res):
    return sorted(f["finding"] for f in json.loads(res[1])["findings"])


class DetectTests(unittest.TestCase):
    def test_closed_verified(self):
        code, raw = run(report([step()]))
        self.assertEqual((code, json.loads(raw)["result"]), (0, "CLOSED_VERIFIED"))
        self.assertEqual(json.loads(raw)["status_ignored"], "closed")

    def test_empty_steps_rejected_even_when_status_closed(self):
        code, raw = run(report([]))
        self.assertEqual(code, 1)
        self.assertIn("empty_steps", findings((code, raw)))

    def test_missing_or_nonindependent_verifier(self):
        for verifier in ("", " ", "\t", "生产方", "生产方 ", "PRODUCER".lower()):
            rep = report([step()], verifier=verifier)
            rep["producer"] = "producer" if verifier == "PRODUCER".lower() else "生产方"
            code, raw = run(rep)
            self.assertEqual(code, 1, verifier)
            self.assertIn("verifier_not_independent", findings((code, raw)))

    def test_verifier_required_field(self):
        rep = report([step()])
        del rep["verifier"]
        self.assertEqual(run(rep)[0], 5)

    def test_unicode_bypasses_of_name_comparison_rejected(self):
        """裁决 6744631746：零宽/全角绕过同名检查必须拒绝，纯零宽视为缺 verifier。"""
        cases = [
            # (verifier, producer, expect_missing)
            ("\u200b", "生产方", True),            # 仅零宽：视为缺失 verifier
            ("\ufeff", "生产方", True),            # 仅 BOM(Cf)：视为缺失
            ("生产方\u200b", "生产方", False),      # 尾零宽：同名，拒绝
            ("生\u200b产方", "生产方", False),      # 中间零宽：同名，拒绝
            ("\u200d生产方", "生产方", False),      # ZWJ 前缀：同名，拒绝
        ]
        for verifier, producer, missing in cases:
            rep = report([step()], verifier=verifier)
            rep["producer"] = producer
            code, raw = run(rep)
            self.assertEqual(code, 1, (verifier, producer))
            fs = findings((code, raw))
            if missing:
                self.assertIn("verifier_not_independent", fs)
                self.assertTrue(any("missing verifier" in f["detail"]
                                    for f in json.loads(raw)["findings"]))

    def test_fullwidth_and_nfkc_bypasses_rejected(self):
        rep = report([step()], verifier="\uff50roducer")  # 全角 p
        rep["producer"] = "producer"
        code, raw = run(rep)
        self.assertEqual(code, 1)
        self.assertIn("verifier_not_independent", findings((code, raw)))

    def test_real_case_difference_still_rejected(self):
        rep = report([step()], verifier="Producer")
        rep["producer"] = "producer"
        code, raw = run(rep)
        self.assertEqual(code, 1)
        self.assertIn("verifier_not_independent", findings((code, raw)))

    def test_distinct_names_still_pass_after_normalization(self):
        rep = report([step()], verifier="验收方\u200b")
        rep["producer"] = "生产方"
        code, _ = run(rep)
        self.assertEqual(code, 0)

    def test_stale_head_sha(self):
        code, raw = run(report([step()]), expected=OTHER_HEAD)
        self.assertEqual(code, 1)
        self.assertIn("stale_head_sha", findings((code, raw)))

    def test_expected_head_missing_or_malformed_is_input_error(self):
        self.assertEqual(run(report([step()]), expected=None)[0], 5)
        self.assertEqual(run(report([step()]), expected="zz")[0], 5)

    def test_history_deleted_loop(self):
        code, raw = run(report([step()], loops=("L2",)), previous=("L1", "L2"))
        self.assertEqual(code, 1)
        got = findings((code, raw))
        self.assertIn("history_deleted", got)

    def test_history_kept_when_loop_present(self):
        code, _ = run(report([step()], loops=("L1",)), previous=("L1",))
        self.assertEqual(code, 0)

    def test_line_misquote(self):
        code, raw = run(report([step(excerpt="hello world")]))
        self.assertEqual(code, 1)
        self.assertIn("misquoted_line", findings((code, raw)))

    def test_line_out_of_range_and_missing_file(self):
        code, raw = run(report([step(line=99)]))
        self.assertIn("line_out_of_range", findings((code, raw)))
        code, raw = run(report([step(path="nope.txt")]))
        self.assertIn("missing_cited_file", findings((code, raw)))

    def test_failed_step_and_digest_mismatch_and_missing_output(self):
        code, raw = run(report([step(exit_code=1)]))
        self.assertIn("step_failed", findings((code, raw)))
        code, raw = run(report([step()]), outputs={"s1": b"tampered\n"})
        self.assertIn("output_digest_mismatch", findings((code, raw)))
        code, raw = run(report([step()]), outputs={})
        self.assertIn("missing_output", findings((code, raw)))

    def test_summary_closed_cannot_override_failed_evidence(self):
        code, raw = run(report([step(exit_code=2), step("s2")], status="closed"),
                        outputs={"s1": b"ok\n", "s2": b"ok\n"})
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(raw)["status_ignored"], "closed")

    def test_all_findings_listed_at_once(self):
        rep = report([step(), step("s2", exit_code=1)], loops=("L2",), head=OTHER_HEAD)
        code, raw = run(rep, previous=("L1",), outputs={"s1": b"ok\n"})
        got = findings((code, raw))
        for expected in ("stale_head_sha", "history_deleted", "step_failed",
                         "missing_output"):
            self.assertIn(expected, got)

    def test_input_errors_exit_5(self):
        base = report([step()])
        bad = report([step()])
        bad["schema_version"] = "loop-closure/v2"
        self.assertEqual(run(bad)[0], 5)
        bad = report([step()])
        bad["extra"] = 1
        self.assertEqual(run(bad)[0], 5)
        self.assertEqual(d.assess(b"", {}, {}, HEAD, [])[0], 5)
        dup = b'{"schema_version":"loop-closure/v1","schema_version":"loop-closure/v1"}'
        self.assertEqual(d.assess(dup, {}, {}, HEAD, [])[0], 5)
        self.assertEqual(run(base, files={"a.txt": "text"})[0], 5)
        self.assertEqual(run(base, previous=["L1", "L1"])[0], 5)

    def test_deterministic_bytes(self):
        first = run(report([step()]))
        second = run(report([step()]))
        self.assertEqual(first, second)
        code, raw = first
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(raw, (json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")) + "\n").encode())

    def test_read_only_no_filesystem_writes(self):
        before = sorted(p.name for p in ROOT.rglob("*"))
        run(report([step()]))
        self.assertEqual(sorted(p.name for p in ROOT.rglob("*")), before)

    def test_version_fingerprint(self):
        proc = subprocess.run([sys.executable, str(ROOT / "detect.py"), "--version"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        digest = hashlib.sha256((ROOT / "detect.py").read_bytes()).hexdigest()
        self.assertEqual(proc.stdout.strip(), f"v1 {digest}")


if __name__ == "__main__":
    unittest.main()
