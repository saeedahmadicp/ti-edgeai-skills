"""layer_cycles.py ranks layers and averages invocations (stdlib only)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "layer_cycles.py"
LOG = """noise
Layer, Layer Cycles, kernel
  1, 1000000, a
  2, 3000000, b
done
Layer, Layer Cycles, kernel
  1, 1000000, a
  2, 1000000, b
"""


class LayerCycles(unittest.TestCase):
    def run_tool(self, *extra):
        f = Path(tempfile.mkdtemp()) / "dbg.log"
        f.write_text(LOG)
        return subprocess.run([sys.executable, str(SCRIPT), str(f), *extra], capture_output=True, text=True)

    def test_average_and_ranking(self):
        r = self.run_tool("--top", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 invocation(s), 2 layers", r.stdout)
        self.assertIn("3.00 ms", r.stdout)  # averaged: layer 1 = 1e6, layer 2 = 2e6 cycles -> 3e6 total = 3 ms at 1 GHz
        lines = [l for l in r.stdout.splitlines() if l.strip().startswith(("1 ", "2 "))]
        self.assertTrue(lines[0].split()[0] == "2")  # layer 2 dominates

    def test_skip_first(self):
        r = self.run_tool("--skip-first")
        self.assertIn("1 invocation(s)", r.stdout)
        self.assertIn("2.00 ms", r.stdout)

    def test_clock_conversion(self):
        r = self.run_tool("--clock-mhz", "500")
        self.assertIn("6.00 ms", r.stdout)

    def test_no_table_is_an_error(self):
        f = Path(tempfile.mkdtemp()) / "empty.log"
        f.write_text("nothing here\n")
        r = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
