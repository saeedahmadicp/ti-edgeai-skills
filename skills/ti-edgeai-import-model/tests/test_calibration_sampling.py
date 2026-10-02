"""Calibration image selection: distinct picks, honest counts, clear errors (stdlib only)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import tidl_preprocess as tp  # noqa: E402


def make_dir(n):
    d = Path(tempfile.mkdtemp())
    for i in range(n):
        (d / f"img{i:03d}.jpg").write_bytes(b"x")
    return d


class Sampling(unittest.TestCase):
    def test_fewer_images_than_requested_are_all_used_once(self):
        picks = tp.pick_images(str(make_dir(10)), 50)
        self.assertEqual(len(picks), 10)
        self.assertEqual(len(set(picks)), 10)

    def test_equal_count(self):
        picks = tp.pick_images(str(make_dir(7)), 7)
        self.assertEqual(len(set(picks)), 7)

    def test_more_images_than_requested_are_spread_and_distinct(self):
        d = make_dir(100)
        picks = tp.pick_images(str(d), 10)
        self.assertEqual(len(set(picks)), 10)
        self.assertTrue(picks[0].endswith("img000.jpg") and picks[-1].endswith("img099.jpg"))

    def test_single_frame(self):
        self.assertEqual(len(tp.pick_images(str(make_dir(5)), 1)), 1)

    def test_empty_directory_is_an_error(self):
        with self.assertRaises(SystemExit):
            tp.pick_images(str(Path(tempfile.mkdtemp())), 5)

    def test_list_file_dedupes_and_checks_existence(self):
        d = make_dir(3)
        lst = d / "list.txt"
        files = sorted(str(p) for p in d.glob("*.jpg"))
        lst.write_text("\n".join(files + files[:1]) + "\n")
        self.assertEqual(len(tp.pick_images(str(lst), 50)), 3)
        lst.write_text("/does/not/exist.jpg\n")
        with self.assertRaises(SystemExit):
            tp.pick_images(str(lst), 5)
        lst.write_text("\n\n")
        with self.assertRaises(SystemExit):
            tp.pick_images(str(lst), 5)

    def test_evenly_spaced_rejects_bad_counts(self):
        with self.assertRaises(ValueError):
            tp.evenly_spaced([1, 2], 0)
        with self.assertRaises(ValueError):
            tp.evenly_spaced([], 3)


if __name__ == "__main__":
    unittest.main()
