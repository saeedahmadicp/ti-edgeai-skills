"""board_host_check.py compare: the comparison gate fails loudly on anything that would make a match meaningless. Needs numpy."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "board_host_check.py"
PREP = json.dumps({"hw": [352, 640], "channels": "bgr"}, sort_keys=True)


def save(path, outs, files=("a.jpg", "b.jpg"), prep=PREP):
    arrays = {f"o{k}_{i:04d}": v[i] for k, v in outs.items() for i in range(len(files))}
    np.savez(path, **arrays, _files=np.array(list(files)), _prep=np.array(prep))


@unittest.skipUnless(np, "numpy not installed")
class Compare(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.base = {0: [np.array([[0.1, 0.9]], np.float32), np.array([[0.7, 0.3]], np.float32)]}

    def cmp(self, a, b, *extra):
        save(self.d / "a.npz", *a[:1], **a[1])
        save(self.d / "b.npz", *b[:1], **b[1])
        return subprocess.run([sys.executable, str(SCRIPT), "compare", str(self.d / "a.npz"), str(self.d / "b.npz"), *extra],
                              capture_output=True, text=True)

    def test_identical_matches(self):
        r = self.cmp((self.base, {}), (self.base, {}))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("MATCH", r.stdout)

    def test_difference_fails_by_default_and_passes_with_tolerance(self):
        other = {0: [self.base[0][0] + 1e-4, self.base[0][1]]}
        self.assertEqual(self.cmp((self.base, {}), (other, {})).returncode, 1)
        self.assertEqual(self.cmp((self.base, {}), (other, {}), "--atol", "1e-3").returncode, 0)

    def test_nan_is_a_failure(self):
        nan = {0: [np.array([[np.nan, 0.9]], np.float32), self.base[0][1]]}
        r = self.cmp((nan, {}), (nan, {}))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("non-finite", r.stdout)

    def test_different_image_lists_fail(self):
        r = self.cmp((self.base, {}), (self.base, {"files": ("a.jpg", "other.jpg")}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("different image lists", r.stdout)

    def test_different_preprocessing_fails(self):
        r = self.cmp((self.base, {}), (self.base, {"prep": json.dumps({"hw": [640, 640]})}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("preprocessing", r.stdout)

    def test_missing_output_fails(self):
        two = {0: self.base[0], 1: [np.zeros(3, np.float32)] * 2}
        r = self.cmp((two, {}), (self.base, {}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("different output sets", r.stdout)

    def test_dtype_and_shape_mismatch_fail(self):
        f64 = {0: [x.astype(np.float64) for x in self.base[0]]}
        self.assertEqual(self.cmp((self.base, {}), (f64, {})).returncode, 1)
        wide = {0: [np.array([[0.1, 0.9, 0.0]], np.float32)] * 2}
        self.assertEqual(self.cmp((self.base, {}), (wide, {})).returncode, 1)


if __name__ == "__main__":
    unittest.main()
