"""Model manifest: validation, hashing, and the shared-preprocessing integration (stdlib only)."""
import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import model_manifest as mm  # noqa: E402
import tidl_preprocess as tp  # noqa: E402


def good(**over):
    m = {"schema_version": 1, "name": "demo", "task": "detection", "input": {"hw": [352, 640], "channels": "bgr", "dtype": "uint8"},
         "classes": ["a", "b"], "postprocess": {"prototxt": "demo.prototxt", "meta_arch_type": 6, "viz_threshold": 0.3},
         "target": {"tools_soc": "am68pa", "tidl_tag": "11_00_06_00", "device": "TDA4VM"}}
    m.update(over)
    return m


class Validate(unittest.TestCase):
    def test_good_manifest_is_valid(self):
        self.assertEqual(mm.validate(good()), [])

    def test_problems_are_reported(self):
        cases = {
            "bad task": good(task="segment"),
            "no input mode": good(input={"channels": "bgr"}),
            "two input modes": good(input={"hw": [1, 2], "letterbox": [1, 2], "channels": "bgr"}),
            "bad hw": good(input={"hw": [0, 640], "channels": "bgr"}),
            "bad channels": good(input={"hw": [8, 8], "channels": "gray"}),
            "crop without resize": good(task="classification", input={"crop": 224, "channels": "rgb"}, classes=["x"]),
            "duplicate classes": good(classes=["a", "a"]),
            "no classes": good(classes=[]),
            "threshold above 1": good(postprocess={"prototxt": "p", "viz_threshold": 2}),
            "detection without prototxt": good(postprocess={}),
            "bad hash": good(files={"a": "short"}),
            "wrong schema": good(schema_version=2),
        }
        for label, m in cases.items():
            with self.subTest(label):
                self.assertTrue(mm.validate(m), label)


class SealVerify(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "model").mkdir()
        (self.root / "artifacts").mkdir()
        (self.root / "model" / "m.onnx").write_bytes(b"onnx")
        (self.root / "artifacts" / "net.bin").write_bytes(b"net")
        (self.root / "param.yaml").write_text("a: 1\n")

    def test_seal_then_verify_then_detect_tampering(self):
        m = mm.seal(good(), self.root)
        self.assertEqual(set(m["files"]), {"model/m.onnx", "artifacts/net.bin", "param.yaml"})
        self.assertEqual(mm.verify(m, self.root), [])
        (self.root / "artifacts" / "net.bin").write_bytes(b"tampered")
        self.assertEqual(mm.verify(m, self.root), ["changed: artifacts/net.bin"])
        (self.root / "model" / "m.onnx").unlink()
        self.assertIn("missing: model/m.onnx", mm.verify(m, self.root))

    def test_file_added_after_sealing_fails_verification(self):
        m = mm.seal(good(), self.root)
        (self.root / "artifacts" / "extra.bin").write_bytes(b"sneaky")
        self.assertEqual(mm.verify(m, self.root), ["unlisted file (added after sealing): artifacts/extra.bin"])
        (self.root / "model" / "second.onnx").write_bytes(b"x")
        self.assertEqual(len(mm.verify(m, self.root)), 2)

    def test_manifest_json_itself_is_not_part_of_the_set(self):
        m = mm.seal(good(), self.root)
        (self.root / "manifest.json").write_text("{}")
        self.assertEqual(mm.verify(m, self.root), [])

    def test_verify_requires_hashes(self):
        self.assertTrue(mm.verify(good(), self.root))

    def test_seal_with_nothing_to_hash_fails(self):
        with self.assertRaises(SystemExit):
            mm.seal(good(), Path(tempfile.mkdtemp()))

    def test_cli_roundtrip(self):
        out = self.root / "m.json"
        tool = str(SCRIPTS / "model_manifest.py")
        r = subprocess.run([sys.executable, tool, "init", "--out", str(out), "--name", "demo", "--task", "detection", "--hw", "352", "640",
                            "--channels", "bgr", "--classes", "a", "--prototxt", "demo.prototxt", "--meta-arch-type", "6"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(subprocess.run([sys.executable, tool, "validate", str(out)]).returncode, 0)
        self.assertEqual(subprocess.run([sys.executable, tool, "seal", str(out), "--root", str(self.root)]).returncode, 0)
        self.assertEqual(subprocess.run([sys.executable, tool, "verify", str(out), "--root", str(self.root)]).returncode, 0)
        (self.root / "param.yaml").write_text("changed\n")
        self.assertEqual(subprocess.run([sys.executable, tool, "verify", str(out), "--root", str(self.root)]).returncode, 1)

    def test_init_rejects_invalid_combination(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / "model_manifest.py"), "init", "--out", str(self.root / "x.json"), "--name", "n",
                            "--task", "detection", "--hw", "8", "8", "--letterbox", "8", "8", "--channels", "bgr", "--classes", "a"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.root / "x.json").exists())


class SharedPreprocessing(unittest.TestCase):
    def parse(self, argv, manifest=None):
        p = argparse.ArgumentParser()
        p.add_argument("--task")
        p.add_argument("--meta-arch-type", type=int)
        tp.add_args(p)
        a = p.parse_args(argv)
        tp.check_args(p, a)
        return a

    def manifest_file(self, m):
        f = Path(tempfile.mkdtemp()) / "m.json"
        f.write_text(json.dumps(m))
        return str(f)

    def test_manifest_supplies_preprocessing(self):
        a = self.parse(["--manifest", self.manifest_file(good())])
        self.assertEqual((a.hw, a.channels, a.input_dtype, a.task, a.meta_arch_type), ([352, 640], "bgr", "uint8", "detection", 6))

    def test_defaults_without_manifest(self):
        a = self.parse(["--hw", "8", "8"])
        self.assertEqual((a.channels, a.input_dtype), ("bgr", "uint8"))

    def test_contradicting_flag_is_an_error(self):
        for extra in (["--hw", "640", "640"], ["--channels", "rgb"], ["--resize", "256", "--crop", "224"]):
            with self.subTest(extra=extra):
                with self.assertRaises(SystemExit):
                    self.parse(["--manifest", self.manifest_file(good()), *extra])

    def test_matching_flag_is_fine(self):
        a = self.parse(["--manifest", self.manifest_file(good()), "--hw", "352", "640", "--channels", "bgr"])
        self.assertEqual(a.hw, [352, 640])

    def test_invalid_manifest_stops_every_tool(self):
        with self.assertRaises(SystemExit):
            self.parse(["--manifest", self.manifest_file(good(task="nope"))])


if __name__ == "__main__":
    unittest.main()
