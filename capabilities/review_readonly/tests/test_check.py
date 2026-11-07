import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check.py"
spec = importlib.util.spec_from_file_location("review_readonly", SCRIPT)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class ReadonlyReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "review"
        self.root.mkdir()
        (self.root / "nested").mkdir()
        (self.root / "a.txt").write_bytes(b"draft\n")
        (self.root / "nested/b.txt").write_bytes(b"unchanged")
        self.paths = ["a.txt", "nested/b.txt"]
        self.raw = c.canonical(c.snapshot(str(self.root), self.paths))
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.baseline = self.base / "before.json"
        self.baseline.write_bytes(self.raw)

    def cli(self, *args):
        p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, timeout=10)
        return p.returncode, json.loads(p.stdout) if p.stdout else None

    def verify_cli(self, digest=None):
        return self.cli("verify", "--root", str(self.root), "--baseline", str(self.baseline),
                        "--baseline-sha256", self.sha if digest is None else digest)

    def test_unchanged_snapshot_deterministic_and_does_not_write(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(self.raw, c.canonical(c.snapshot(str(self.root), list(reversed(self.paths)))))
        code, out = self.verify_cli()
        self.assertEqual((code, out["verdict"], out["delivery_allowed"]), (0, "UNCHANGED", True))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_same_size_edit_and_append_block_delivery(self):
        for value in (b"craft\n", b"draft\nextra"):
            (self.root / "a.txt").write_bytes(value)
            code, out = self.verify_cli()
            self.assertEqual((code, out["changed"], out["delivery_allowed"]), (1, ["a.txt"], False))

    def test_deleted_file_or_directory_is_changed(self):
        (self.root / "nested/b.txt").unlink()
        (self.root / "nested").rmdir()
        code, out = self.verify_cli()
        self.assertEqual((code, out["changed"], out["actual"]["nested/b.txt"]), (1, ["nested/b.txt"], None))

    def test_renamed_file_is_not_silently_accepted(self):
        (self.root / "a.txt").rename(self.root / "new.txt")
        self.assertEqual(self.verify_cli()[0], 1)

    def test_modified_manifest_cannot_replace_trusted_digest(self):
        (self.root / "a.txt").write_bytes(b"modified")
        self.baseline.write_bytes(c.canonical(c.snapshot(str(self.root), self.paths)))
        code, out = self.verify_cli()
        self.assertEqual((code, out["verdict"], out["delivery_allowed"]), (5, "INPUT_ERROR", False))

    def test_bad_or_missing_digest_is_not_accepted(self):
        for digest in ("", "0" * 64, "F" * 64):
            self.assertEqual(self.verify_cli(digest)[0], 5)
        self.assertEqual(self.cli("verify", "--root", str(self.root), "--baseline", str(self.baseline))[0], 2)

    def test_other_root_cannot_substitute_same_files(self):
        other = self.base / "other"
        other.mkdir()
        code, out = self.cli("verify", "--root", str(other), "--baseline", str(self.baseline),
                             "--baseline-sha256", self.sha)
        self.assertEqual((code, out["delivery_allowed"]), (5, False))

    def test_invalid_paths_duplicate_targets_and_empty_set(self):
        for paths in ([], ["a.txt", "a.txt"], ["../outside"], ["/a.txt"], ["nested//b.txt"],
                      ["nested/./b.txt"], ["a\\b"], ["a:b"], ["a\0b"]):
            with self.assertRaises(c.InputError, msg=paths):
                c.snapshot(str(self.root), paths)

    def test_target_and_intermediate_symlinks_are_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "file").write_text("outside")
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        (self.root / "alias").symlink_to(outside / "file")
        for path in ("link/file", "alias"):
            self.assertEqual(self.cli("snapshot", "--root", str(self.root), "--file", path)[0], 5)
        (self.root / "a.txt").unlink()
        (self.root / "a.txt").symlink_to(outside / "file")
        self.assertEqual(self.verify_cli()[0], 5)

    def test_symlink_root_and_baseline_are_rejected(self):
        rootlink = self.base / "rootlink"
        rootlink.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.cli("snapshot", "--root", str(rootlink), "--file", "a.txt")[0], 5)
        link = self.base / "baseline-link"
        link.symlink_to(self.baseline)
        self.assertEqual(self.cli("verify", "--root", str(self.root), "--baseline", str(link),
                                  "--baseline-sha256", self.sha)[0], 5)

    def test_fifo_and_directory_do_not_block_or_pass(self):
        os.mkfifo(self.root / "pipe")
        for path in ("pipe", "nested"):
            self.assertEqual(self.cli("snapshot", "--root", str(self.root), "--file", path)[0], 5)

    def test_malformed_duplicate_json_empty_and_invalid_metadata(self):
        base = json.loads(self.raw)
        variants = [b"{", b"\xff", b'{"files":{},"files":{}}',
                    c.canonical(dict(base, extra=True)), c.canonical(dict(base, files={})),
                    c.canonical(dict(base, files={"../bad": {"bytes": 0, "sha256": "0" * 64}})),
                    c.canonical(dict(base, files={"a.txt": {"bytes": True, "sha256": "0" * 64}}))]
        for raw in variants:
            self.baseline.write_bytes(raw)
            code, out = self.verify_cli(hashlib.sha256(raw).hexdigest())
            self.assertEqual((code, out["delivery_allowed"]), (5, False))

    def test_bounded_file_and_manifest_size(self):
        with (self.root / "huge").open("wb") as f:
            f.truncate(c.MAX_FILE + 1)
        self.assertEqual(self.cli("snapshot", "--root", str(self.root), "--file", "huge")[0], 5)
        self.baseline.write_bytes(b" " * (c.MAX_MANIFEST + 1))
        self.assertEqual(self.verify_cli()[0], 5)

    def test_empty_file_is_valid_and_content_is_inert(self):
        (self.root / "empty").write_bytes(b"")
        marker = self.base / "pwned"
        (self.root / "commands").write_text("$(touch " + str(marker) + ")")
        for path in ("empty", "commands"):
            code, out = self.cli("snapshot", "--root", str(self.root), "--file", path)
            self.assertEqual(code, 0)
            self.assertEqual(out["files"][path]["sha256"], hashlib.sha256((self.root / path).read_bytes()).hexdigest())
        self.assertFalse(marker.exists())

    def test_real_cli_exit_blocks_delivery_command(self):
        marker = self.base / "delivered"
        command = '"$1" "$2" verify --root "$3" --baseline "$4" --baseline-sha256 "$5" && touch "$6"'
        args = ["/bin/sh", "-c", command, "gate", sys.executable, str(SCRIPT), str(self.root),
                str(self.baseline), self.sha, str(marker)]
        result = subprocess.run(args, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(marker.exists())
        marker.unlink()
        (self.root / "a.txt").write_bytes(b"edited")
        result = subprocess.run(args, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(marker.exists())

    def test_modify_then_restore_is_explicit_observation_limit(self):
        # No polling/hash-only checker proves that there was no intermediate write.
        (self.root / "a.txt").write_bytes(b"temporary edit")
        (self.root / "a.txt").write_bytes(b"draft\n")
        self.assertEqual(self.verify_cli()[0], 0)

    def take_snapshot(self, *extra):
        p = subprocess.run([sys.executable, str(SCRIPT), "snapshot", "--root", str(self.root), *extra],
                           capture_output=True, timeout=10)
        parsed = json.loads(p.stdout) if p.stdout else None
        self.assertEqual(p.returncode, 0, parsed or p.stderr)
        self.baseline.write_bytes(p.stdout)
        self.raw = p.stdout
        self.sha = hashlib.sha256(p.stdout).hexdigest()
        return parsed

    def test_crlf_rewrite_is_a_byte_change(self):
        (self.root / "a.txt").write_bytes(b"draft\r\n")
        code, out = self.verify_cli()
        self.assertEqual((code, out["changed"], out["delivery_allowed"]), (1, ["a.txt"], False))
        self.take_snapshot("--file", "a.txt")
        self.assertEqual(self.verify_cli()[0], 0)

    def test_file_changed_while_reading_exits_5(self):
        target = self.root / "a.txt"
        real_read = os.read

        def hooked(fd, n):
            data = real_read(fd, n)
            if not hooked.done:
                hooked.done = True
                target.write_bytes(b"mutated-while-reading")
            return data

        hooked.done = False
        os.read = hooked
        stdout = sys.stdout
        wrapper = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        sys.stdout = wrapper
        try:
            code = c.main(["snapshot", "--root", str(self.root), "--file", "a.txt"])
            payload = json.loads(wrapper.buffer.getvalue())
        finally:
            sys.stdout = stdout
            os.read = real_read
            wrapper.close()
        self.assertEqual(code, 5, payload)
        self.assertEqual(payload["verdict"], "INPUT_ERROR")
        self.assertFalse(payload["delivery_allowed"])
        self.assertIn("changed while reading", payload["reason"])

    def test_file_mode_ignores_unlisted_new_file(self):
        (self.root / "extra.txt").write_bytes(b"extra")
        code, out = self.verify_cli()
        self.assertEqual((code, out["verdict"], out["delivery_allowed"]), (0, "UNCHANGED", True))
        self.assertNotIn("trees", json.loads(self.raw))

    def test_tree_new_file_is_added(self):
        manifest = self.take_snapshot("--tree", ".")
        self.assertEqual(manifest["trees"], ["."])
        self.assertEqual(self.verify_cli()[0], 0)
        (self.root / "extra.txt").write_bytes(b"extra")
        code, out = self.verify_cli()
        self.assertEqual(code, 1)
        self.assertEqual(out["changed"], {"added": ["extra.txt"], "removed": [], "modified": []})
        self.assertFalse(out["delivery_allowed"])

    def test_tree_deleted_file_is_removed(self):
        self.take_snapshot("--tree", ".")
        (self.root / "nested" / "b.txt").unlink()
        code, out = self.verify_cli()
        self.assertEqual((code, out["changed"]["removed"], out["delivery_allowed"]),
                         (1, ["nested/b.txt"], False))

    def test_tree_rename_is_added_and_removed(self):
        self.take_snapshot("--tree", ".")
        (self.root / "a.txt").rename(self.root / "z.txt")
        code, out = self.verify_cli()
        self.assertEqual((code, out["changed"]), (1, {
            "added": ["z.txt"], "removed": ["a.txt"], "modified": []}))

    def test_tree_new_file_in_subdirectory(self):
        self.take_snapshot("--tree", "nested")
        (self.root / "nested" / "c.txt").write_bytes(b"c")
        (self.root / "extra.txt").write_bytes(b"outside this tree")
        code, out = self.verify_cli()
        self.assertEqual((code, out["changed"]["added"], out["delivery_allowed"]),
                         (1, ["nested/c.txt"], False))

    def test_tree_same_size_edit_is_modified(self):
        self.take_snapshot("--tree", ".")
        (self.root / "a.txt").write_bytes(b"craft\n")
        code, out = self.verify_cli()
        self.assertEqual((code, out["changed"]["modified"]), (1, ["a.txt"]))

    def test_tree_symlink_directory_fifo_and_nested_symlink_are_rejected(self):
        (self.root / "linked").symlink_to(self.root / "nested", target_is_directory=True)
        code, out = self.cli("snapshot", "--root", str(self.root), "--tree", "linked")
        self.assertEqual((code, out["delivery_allowed"]), (5, False))
        (self.root / "nested" / "alias").symlink_to(self.root / "a.txt")
        self.assertEqual(self.cli("snapshot", "--root", str(self.root), "--tree", "nested")[0], 5)
        fifo_dir = self.root / "fifodir"
        fifo_dir.mkdir()
        os.mkfifo(fifo_dir / "pipe")
        self.assertEqual(self.cli("snapshot", "--root", str(self.root), "--tree", "fifodir")[0], 5)

    def test_tree_duplicate_or_missing_selector_is_rejected(self):
        self.assertEqual(self.cli("snapshot", "--root", str(self.root))[0], 2)
        self.assertEqual(self.cli("snapshot", "--root", str(self.root), "--tree", "nested", "--tree", "nested")[0], 5)

    def test_invalid_tree_metadata_is_rejected(self):
        base = json.loads(self.raw)
        for trees in (["../x"], [".", "."], "nested", [], ["a.txt"]):
            raw = c.canonical(dict(base, trees=trees))
            self.baseline.write_bytes(raw)
            code, out = self.verify_cli(hashlib.sha256(raw).hexdigest())
            self.assertEqual((code, out["delivery_allowed"]), (5, False), trees)

    def test_baseline_inside_review_root_is_rejected(self):
        inside = self.root / "before.json"
        inside.write_bytes(self.raw)
        code, out = self.cli("verify", "--root", str(self.root), "--baseline", str(inside),
                             "--baseline-sha256", self.sha)
        self.assertEqual((code, out["verdict"], out["delivery_allowed"]), (5, "INPUT_ERROR", False))
        self.assertIn("inside", out["reason"])
        alias = self.base / "alias-parent"
        alias.symlink_to(self.root, target_is_directory=True)
        code, out = self.cli("verify", "--root", str(self.root), "--baseline", str(alias / "before.json"),
                             "--baseline-sha256", self.sha)
        self.assertEqual((code, out["delivery_allowed"]), (5, False))

    def test_baseline_hardlink_inside_tree_is_rejected(self):
        self.take_snapshot("--tree", ".")
        os.link(self.baseline, self.root / "alias.json")
        code, out = self.verify_cli()
        self.assertEqual((code, out["verdict"], out["delivery_allowed"]), (5, "INPUT_ERROR", False))
        self.assertIn("inode", out["reason"])

    def test_empty_tree_then_add_is_changed(self):
        empty = self.root / "empty"
        empty.mkdir()
        manifest = self.take_snapshot("--tree", "empty")
        self.assertEqual(manifest["files"], {})
        self.assertEqual(self.verify_cli()[0], 0)
        (empty / "a.txt").write_bytes(b"a")
        code, out = self.verify_cli()
        self.assertEqual((code, out["changed"]["added"]), (1, ["empty/a.txt"]))

    def test_tree_works_when_dev_fd_is_not_listable(self):
        # Regression for #47: on macOS /dev/fd/N exists but cannot be used
        # as a directory, and /proc/self/fd does not exist, so every
        # --tree call failed closed with exit 5. Listing the directory
        # descriptor directly must work there. The simulation runs the CLI
        # in a subprocess with a sitecustomize that hides /proc/self/fd
        # and makes os.listdir('/dev/fd/N') raise ENOTDIR, so the test
        # also runs on Linux CI and in Hark's sandbox; a real macOS
        # machine is still NOT_TESTED here.
        sim = self.base / "macos_sim"
        sim.mkdir()
        (sim / "sitecustomize.py").write_text(
            "import os\n"
            "_listdir = os.listdir\n"
            "def _fake_listdir(path):\n"
            "    if isinstance(path, str) and path.startswith('/dev/fd/'):\n"
            "        raise NotADirectoryError(20, 'Not a directory', path)\n"
            "    return _listdir(path)\n"
            "os.listdir = _fake_listdir\n"
            "_exists = os.path.exists\n"
            "def _fake_exists(p):\n"
            "    if isinstance(p, str) and p.startswith('/proc/self/fd'):\n"
            "        return False\n"
            "    return _exists(p)\n"
            "os.path.exists = _fake_exists\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(sim) + os.pathsep + env.get("PYTHONPATH", "")
        p = subprocess.run(
            [sys.executable, str(SCRIPT), "snapshot", "--root", str(self.root), "--tree", "."],
            capture_output=True, timeout=10, env=env,
        )
        manifest = json.loads(p.stdout) if p.stdout else None
        self.assertEqual(p.returncode, 0, manifest or p.stderr)
        self.assertEqual(sorted(manifest["files"]), ["a.txt", "nested/b.txt"])
        self.assertEqual(manifest["trees"], ["."])
        self.baseline.write_bytes(c.canonical(manifest))
        self.sha = hashlib.sha256(c.canonical(manifest)).hexdigest()
        p = subprocess.run(
            [sys.executable, str(SCRIPT), "verify", "--root", str(self.root),
             "--baseline", str(self.baseline), "--baseline-sha256", self.sha],
            capture_output=True, timeout=10, env=env,
        )
        out = json.loads(p.stdout) if p.stdout else None
        self.assertEqual((p.returncode, out["verdict"], out["delivery_allowed"]),
                         (0, "UNCHANGED", True))


if __name__ == "__main__":
    unittest.main()
