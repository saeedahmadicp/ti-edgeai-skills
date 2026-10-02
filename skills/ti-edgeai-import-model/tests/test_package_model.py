"""package_model.py contracts: no silent assumptions about shapes, outputs or offload. Needs PyYAML (and onnx for the model tests)."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import yaml  # noqa: F401
except ImportError:  # pragma: no cover
    yaml = None
try:
    import onnx
    from onnx import TensorProto, helper
except ImportError:  # pragma: no cover
    onnx = None

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "package_model.py"


def load_module():
    spec = importlib.util.spec_from_file_location("package_model", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_artifacts(d, allowed, total=None, out_names="dets,labels"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "allowedNode.txt").write_text(allowed)
    (d / "onnxrtMetaData.txt").write_text(f"numGraphNodes={total}\n0:outDataNames={out_names}\n" if total is not None else "")
    (d / "subgraph_0_tidl_net.bin").write_bytes(b"x")
    (d / "subgraph_0_tidl_io_1.bin").write_bytes(b"x")


@unittest.skipUnless(yaml, "PyYAML not installed")
class Coverage(unittest.TestCase):
    def setUp(self):
        self.m = load_module()
        self.d = Path(tempfile.mkdtemp())

    def test_full_offload(self):
        write_artifacts(self.d, "1\n3\n0\n1\n2\n", total=3)
        self.assertEqual(self.m.offload_coverage(self.d), (1, 3, 3))

    def test_one_subgraph_is_not_full_offload(self):
        write_artifacts(self.d, "1\n3\n0\n1\n2\n", total=10)
        self.assertEqual(self.m.offload_coverage(self.d), (1, 3, 10))

    def test_two_subgraphs(self):
        write_artifacts(self.d, "2\n2\n0\n1\n1\n5\n", total=9)
        self.assertEqual(self.m.offload_coverage(self.d), (2, 3, 9))

    def test_unexpected_layout_is_unknown_not_guessed(self):
        write_artifacts(self.d, "1\n3\n0\n1\n", total=3)       # count says 3 ids, only 2 present
        self.assertIsNone(self.m.offload_coverage(self.d))
        write_artifacts(self.d, "garbage", total=3)
        self.assertIsNone(self.m.offload_coverage(self.d))
        write_artifacts(self.d, "1\n3\n0\n1\n2\n", total=None)
        self.assertIsNone(self.m.offload_coverage(self.d))

    def test_keep_top_k_from_prototxt(self):
        f = self.d / "m.prototxt"
        f.write_text("detection_output_param { keep_top_k: 150 }")
        self.assertEqual(self.m.keep_top_k(f), 150)
        f.write_text("nothing")
        self.assertIsNone(self.m.keep_top_k(f))


@unittest.skipUnless(yaml and onnx, "PyYAML and onnx are required")
class Packaging(unittest.TestCase):
    def make_onnx(self, shape):
        x = helper.make_tensor_value_info("images", TensorProto.UINT8, shape)
        y = helper.make_tensor_value_info("scores", TensorProto.FLOAT, [1, 3])
        node = helper.make_node("Identity", ["images"], ["scores"])
        m = helper.make_model(helper.make_graph([node], "g", [x], [y]))
        p = Path(tempfile.mkdtemp()) / "m.onnx"
        onnx.save(m, p)
        return p

    def run_pkg(self, onnx_path, artifacts, *extra):
        out = Path(tempfile.mkdtemp())
        return subprocess.run([sys.executable, str(SCRIPT), "--onnx", str(onnx_path), "--artifacts", str(artifacts), "--out-dir", str(out),
                               "--name", "pkg", *extra], capture_output=True, text=True), out

    def test_dynamic_input_is_refused_not_turned_into_one(self):
        art = Path(tempfile.mkdtemp())
        write_artifacts(art, "1\n1\n0\n", total=1)
        r, out = self.run_pkg(self.make_onnx(["batch", 3, 8, 8]), art, "--task", "classification", "--resize", "8", "--crop", "8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dynamic", r.stdout + r.stderr)
        self.assertFalse((out / "pkg").exists())

    def test_classification_packaging_reports_coverage_honestly(self):
        art = Path(tempfile.mkdtemp())
        write_artifacts(art, "1\n1\n0\n", total=4)
        r, out = self.run_pkg(self.make_onnx([1, 3, 8, 8]), art, "--task", "classification", "--resize", "8", "--crop", "8",
                              "--classes", "a", "b", "c")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1/4 graph nodes", r.stdout)
        self.assertIn("3 node(s) run on ARM", r.stdout)

    def test_detection_without_metadata_is_refused(self):
        art = Path(tempfile.mkdtemp())
        write_artifacts(art, "1\n1\n0\n", total=None)
        proto = art / "m.prototxt"
        proto.write_text("keep_top_k: 100")
        r, _ = self.run_pkg(self.make_onnx([1, 3, 8, 8]), art, "--task", "detection", "--hw", "8", "8", "--classes", "a",
                            "--prototxt", str(proto))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("cannot derive the detection output contract", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
