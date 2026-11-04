"""INSTALL.md「已发布版本指纹」必须与 check.py --version 及文件 sha256 一致。

本节缺失、登记值彼此不一致，或与当前 check.py 不符时，本测试失败。
只读 INSTALL.md，不执行其中的命令。
"""
import hashlib
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "INSTALL.md"
SCRIPT = ROOT / "check.py"
HEADING = "已发布版本指纹"
REGISTERED = re.compile(r"版本号是 `([^`\n]+)`，sha256 是 `([0-9a-f]{64})`")
FENCE_LINE = re.compile(r"(?m)^(v\d+(?:\.\d+)*) ([0-9a-f]{64})$")
INLINE = re.compile(r"`(v\d+(?:\.\d+)*) ([0-9a-f]{64})`")
SHA256 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
VERSION = re.compile(r"^v\d+(?:\.\d+)*$")


def published_section(text):
    match = re.search(rf"(?m)^## {re.escape(HEADING)}[ \t]*$", text)
    if not match:
        return None
    rest = text[match.end():]
    nxt = re.search(r"(?m)^## ", rest)
    return rest[:nxt.start()] if nxt else rest


class PublishedFingerprint(unittest.TestCase):
    def test_registered_version_and_sha256_match_check_py(self):
        section = published_section(INSTALL.read_text(encoding="utf-8"))
        self.assertIsNotNone(section, "INSTALL.md 缺少「已发布版本指纹」")
        registered = REGISTERED.findall(section)
        self.assertEqual(
            len(registered), 1,
            "「已发布版本指纹」必须登记唯一的版本号与 sha256",
        )
        version, digest = registered[0]
        self.assertRegex(version, VERSION)

        digests = SHA256.findall(section)
        self.assertEqual(set(digests), {digest}, "节内 sha256 与登记值不一致")

        pairs = FENCE_LINE.findall(section) + INLINE.findall(section)
        self.assertTrue(pairs, "「已发布版本指纹」没有版本号与 sha256 对照行")
        self.assertTrue(all(item == (version, digest) for item in pairs), pairs)

        actual = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        self.assertEqual(digest, actual, "登记的 sha256 与 check.py 文件不一致")

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--version"],
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode(), f"{version} {digest}\n")


if __name__ == "__main__":
    unittest.main()
