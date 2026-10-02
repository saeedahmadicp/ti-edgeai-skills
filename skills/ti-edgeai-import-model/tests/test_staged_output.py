"""staged_output: a failed build never destroys the previous good output (stdlib only)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import staged_output as so  # noqa: E402


class Staged(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.dest = self.root / "artifacts"

    def test_abort_leaves_previous_output_untouched(self):
        self.dest.mkdir()
        (self.dest / "net.bin").write_text("good")
        staging = so.begin(self.dest)
        (staging / "partial.bin").write_text("half")
        so.abort(staging)
        self.assertEqual((self.dest / "net.bin").read_text(), "good")
        self.assertFalse(staging.exists())

    def test_commit_keeps_previous_as_sibling(self):
        self.dest.mkdir()
        (self.dest / "net.bin").write_text("old")
        staging = so.begin(self.dest)
        (staging / "net.bin").write_text("new")
        previous = so.commit(staging, self.dest)
        self.assertEqual((self.dest / "net.bin").read_text(), "new")
        self.assertEqual((previous / "net.bin").read_text(), "old")

    def test_first_commit_has_no_previous(self):
        staging = so.begin(self.dest)
        (staging / "x").write_text("1")
        self.assertIsNone(so.commit(staging, self.dest))
        self.assertTrue((self.dest / "x").exists())

    def test_two_commits_in_one_second_do_not_collide(self):
        for text in ("a", "b", "c"):
            staging = so.begin(self.dest)
            (staging / "v").write_text(text)
            so.commit(staging, self.dest)
        self.assertEqual((self.dest / "v").read_text(), "c")
        self.assertEqual(len(list(self.root.glob("artifacts.previous-*"))), 2)


if __name__ == "__main__":
    unittest.main()
