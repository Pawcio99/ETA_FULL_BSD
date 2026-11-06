"""Independent stdlib tests of W01 read-only scanner on synthetic fixtures."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/w01_source_identity.py"


class W01Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "source"
        self.root.mkdir()
        (self.root / "tools").mkdir()
        self.f = self.root / "tools" / "a.py"
        self.f.write_bytes(b"# source\n")
        self.expected = hashlib.sha256(self.f.read_bytes()).hexdigest()

    def invoke(self, *extra, root=None):
        args = [sys.executable, "-B", str(SCRIPT), "--source-root", str(root or self.root), "--file", "tools/a.py", *extra]
        r = subprocess.run(args, text=True, capture_output=True, check=False, timeout=5)
        return r.returncode, json.loads(r.stdout), r.stderr

    def test_happy_readonly(self):
        original = self.f.read_bytes()
        rc, out, _ = self.invoke("--expect", "tools/a.py=" + self.expected)
        self.assertEqual(rc, 0)
        self.assertEqual(out["files"]["tools/a.py"]["sha256"], self.expected)
        self.assertFalse(out["complete_tree_attested"])
        self.assertEqual(self.f.read_bytes(), original)
        self.assertEqual(list(self.root.rglob("*.pyc")), [])

    def test_wrong_digest(self):
        rc, out, _ = self.invoke("--expect", "tools/a.py=" + "0" * 64)
        self.assertEqual(rc, 20)
        self.assertEqual(out["mismatched"], ["tools/a.py"])

    def test_missing_file(self):
        self.f.unlink()
        self.assertEqual(self.invoke()[0], 21)

    def test_link_final(self):
        self.f.unlink()
        self.f.symlink_to("/etc/passwd")
        self.assertEqual(self.invoke()[0], 21)

    def test_link_directory(self):
        (self.root / "tools").rename(self.root / "moved")
        (self.root / "tools").symlink_to(self.root / "moved", target_is_directory=True)
        self.assertEqual(self.invoke()[0], 21)

    def test_link_root(self):
        aliased = Path(self.tmp.name) / "alias"
        aliased.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.invoke(root=aliased)[0], 21)

    def test_parent_traversal(self):
        self.assertEqual(self.invoke("--file", "../etc/passwd")[0], 21)

    def test_invalid_expect(self):
        self.assertEqual(self.invoke("--expect", "tools/a.py=bad")[0], 21)

    def test_duplicate_expect(self):
        x = "tools/a.py=" + self.expected
        self.assertEqual(self.invoke("--expect", x, "--expect", x)[0], 21)

    def test_manifest_checkpoint_hashed_without_executing(self):
        (self.root / "man.sha256").write_bytes(b"deadbeef  src\n")
        (self.root / "checkpoint.json").write_bytes(b'{"state":"DRAFT"}\n')
        rc, out, _ = self.invoke("--manifest", "man.sha256", "--checkpoint", "checkpoint.json")
        self.assertEqual(rc, 0)
        self.assertEqual(out["selected_file_count"], 3)
        self.assertEqual(out["g0"], "BLOCKED_PENDING_W01_W04_EVIDENCE")

    def test_directory_rejected_as_file(self):
        self.assertEqual(self.invoke("--file", "tools")[0], 21)

    def test_overlarge_file_refused(self):
        with self.f.open("wb") as f:
            f.truncate(32 * 1024 * 1024 + 1)
        self.assertEqual(self.invoke()[0], 21)


if __name__ == "__main__":
    unittest.main(verbosity=2)
