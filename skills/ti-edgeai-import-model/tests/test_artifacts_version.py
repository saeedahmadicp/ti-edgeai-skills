"""check_artifacts_version.py compares the 4-byte format stamp against a reference (stdlib only)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_artifacts_version.py"


def run(mine, ref):
    d = Path(tempfile.mkdtemp())
    (d / "mine.bin").write_bytes(mine + b"\0" * 8)
    (d / "ref.bin").write_bytes(ref + b"\0" * 8)
    return subprocess.run([sys.executable, str(SCRIPT), str(d / "mine.bin"), "--ref", str(d / "ref.bin")],
                          capture_output=True, text=True)


class ArtifactsVersion(unittest.TestCase):
    def test_same_stamp_ok(self):
        r = run(bytes.fromhex("29042520"), bytes.fromhex("29042520"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("OK", r.stdout)

    def test_different_stamp_fails(self):
        r = run(bytes.fromhex("30062520"), bytes.fromhex("29042520"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISMATCH", r.stdout)

    def test_needs_a_reference(self):
        d = Path(tempfile.mkdtemp()) / "m.bin"
        d.write_bytes(b"\0" * 16)
        r = subprocess.run([sys.executable, str(SCRIPT), str(d)], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
