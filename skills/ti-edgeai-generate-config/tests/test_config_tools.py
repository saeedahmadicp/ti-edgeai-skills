"""generate_config.py output passes validate_config.py; broken configs are rejected. Needs PyYAML."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

SKILL = Path(__file__).resolve().parent.parent
GEN = SKILL / "scripts" / "generate_config.py"
VAL = SKILL / "scripts" / "validate_config.py"
MODEL = "/opt/model_zoo/ONR-OD-8200-yolox-nano-lite-mmdet-coco-416x416"


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


@unittest.skipUnless(yaml, "PyYAML not installed")
class ConfigTools(unittest.TestCase):
    def generate(self, *args):
        out = Path(tempfile.mkdtemp()) / "c.yaml"
        r = run(GEN, *args, "--model", MODEL, "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return out

    def test_generated_configs_validate(self):
        cases = [
            ["--input", "video", "--source", "/opt/edgeai-test-data/videos/video0_1280_768.h264", "--format", "h264",
             "--width", "1280", "--height", "768", "--output", "file", "--sink", "/opt/edgeai-test-data/output/t.mkv"],
            ["--input", "usb", "--source", "/dev/video2", "--format", "auto", "--width", "640", "--height", "360",
             "--output", "fakesink"],
            ["--input", "usb", "--source", "/dev/video2", "--format", "auto", "--width", "640", "--height", "360",
             "--output", "display", "--perf-overlay", "graph"],
        ]
        for args in cases:
            with self.subTest(args=args):
                cfg = self.generate(*args)
                r = run(VAL, str(cfg))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_shipped_examples_validate(self):
        for f in sorted((SKILL / "assets").glob("example_*.yaml")):
            with self.subTest(f=f.name):
                r = run(VAL, str(f))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_output_larger_than_input_is_rejected(self):
        cfg = yaml.safe_load((SKILL / "assets" / "example_video.yaml").read_text())
        cfg["outputs"]["output0"]["width"] = 1920
        cfg["outputs"]["output0"]["height"] = 1080
        bad = Path(tempfile.mkdtemp()) / "bad.yaml"
        bad.write_text(yaml.safe_dump(cfg))
        r = run(VAL, str(bad))
        self.assertNotEqual(r.returncode, 0, r.stdout)

    def test_unknown_reference_is_rejected(self):
        cfg = yaml.safe_load((SKILL / "assets" / "example_video.yaml").read_text())
        cfg["flows"]["flow0"] = ["input0", "model_missing", "output0"]
        bad = Path(tempfile.mkdtemp()) / "bad.yaml"
        bad.write_text(yaml.safe_dump(cfg))
        self.assertNotEqual(run(VAL, str(bad)).returncode, 0)

    # --- contracts found by review: serialization safety, types, ranges -------------------------------------------------
    def validate_dict(self, cfg):
        bad = Path(tempfile.mkdtemp()) / "c.yaml"
        bad.write_text(yaml.safe_dump(cfg))
        return run(VAL, str(bad))

    def base(self):
        return yaml.safe_load((SKILL / "assets" / "example_video.yaml").read_text())

    def test_title_with_quotes_and_colons_is_valid_yaml(self):
        cfg = self.generate("--input", "usb", "--width", "640", "--height", "360", "--output", "fakesink",
                            "--title", 'My "quoted": title # not a comment')
        data = yaml.safe_load(cfg.read_text())
        self.assertEqual(data["title"], 'My "quoted": title # not a comment')
        self.assertEqual(run(VAL, str(cfg)).returncode, 0)

    def test_generator_rejects_bad_numbers(self):
        for extra in (["--width", "-640", "--height", "360"], ["--width", "640", "--height", "0"],
                      ["--width", "640", "--height", "360", "--port", "70000"],
                      ["--width", "640", "--height", "360", "--viz-threshold", "1.5"],
                      ["--width", "640", "--height", "360", "--out-width", "-1"]):
            with self.subTest(extra=extra):
                r = run(GEN, "--input", "usb", "--model", MODEL, "--output", "fakesink", *extra)
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn("Traceback", r.stderr)

    def test_validator_rejects_wrong_types_and_ranges_without_traceback(self):
        cases = {
            "negative input width": lambda c: c["inputs"]["input0"].__setitem__("width", -1280),
            "string input height": lambda c: c["inputs"]["input0"].__setitem__("height", "768"),
            "zero output width": lambda c: c["outputs"]["output0"].__setitem__("width", 0),
            "bool dimension": lambda c: c["inputs"]["input0"].__setitem__("width", True),
            "threshold above 1": lambda c: c["models"]["model0"].__setitem__("viz_threshold", 2),
            "negative framerate": lambda c: c["inputs"]["input0"].__setitem__("framerate", -30),
            "loop not boolean": lambda c: c["inputs"]["input0"].__setitem__("loop", "yes please"),
            "input is not a mapping": lambda c: c["inputs"].__setitem__("input0", "oops"),
            "empty source": lambda c: c["inputs"]["input0"].__setitem__("source", ""),
            "port out of range": lambda c: c["outputs"]["output0"].update(port=0),
            "mosaic negative origin": lambda c: c["flows"].__setitem__("flow0", ["input0", "model0", "output0", [-5, 0, 100, 100]]),
            "mosaic zero size": lambda c: c["flows"].__setitem__("flow0", ["input0", "model0", "output0", [0, 0, 0, 100]]),
            "mosaic non-integer": lambda c: c["flows"].__setitem__("flow0", ["input0", "model0", "output0", [0, 0, "a", 100]]),
            "output reference is a list": lambda c: c["flows"].__setitem__("flow0", ["input0", "model0", ["output0"]]),
            "input reference is a mapping": lambda c: c["flows"].__setitem__("flow0", [{"a": 1}, "model0", "output0"]),
            "model reference is null": lambda c: c["flows"].__setitem__("flow0", ["input0", None, "output0"]),
            "flow is a string": lambda c: c["flows"].__setitem__("flow0", "input0,model0,output0"),
            "flows is a list": lambda c: c.__setitem__("flows", ["input0"]),
            "models is a string": lambda c: c.__setitem__("models", "model0"),
            "mosaic outside output": lambda c: c["flows"].__setitem__("flow0", ["input0", "model0", "output0", [1000, 0, 500, 100]]),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                cfg = self.base()
                mutate(cfg)
                r = self.validate_dict(cfg)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertNotIn("Traceback", r.stderr, r.stderr)
                self.assertIn("ERROR", r.stdout)

    def test_validator_handles_non_mapping_and_broken_yaml(self):
        for text in ("", "- a\n- b\n", "inputs: [unclosed\n"):
            with self.subTest(text=text):
                f = Path(tempfile.mkdtemp()) / "c.yaml"
                f.write_text(text)
                r = run(VAL, str(f))
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn("Traceback", r.stderr, r.stderr)


@unittest.skipUnless(yaml, "PyYAML not installed")
class Fuzz(unittest.TestCase):
    """Random wrong types anywhere in a valid config must produce validation errors, never an exception."""

    def test_random_mutations_never_crash(self):
        import copy
        import importlib.util
        import random
        spec = importlib.util.spec_from_file_location("validate_config", VAL)
        vc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vc)
        base = yaml.safe_load((SKILL / "assets" / "example_mosaic.yaml").read_text())
        weird = [None, [], {}, "", "x", -1, 0, 3.5, True, [1, 2], ["a"], {"a": 1}, 10 ** 12, float("nan")]
        rng = random.Random(1234)

        def paths(node, prefix=()):
            yield prefix
            if isinstance(node, dict):
                for k, v in node.items():
                    yield from paths(v, prefix + (k,))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    yield from paths(v, prefix + (i,))

        for i in range(400):
            cfg = copy.deepcopy(base)
            for _ in range(rng.randint(1, 3)):
                path = rng.choice([p for p in paths(cfg) if p])
                node = cfg
                for k in path[:-1]:
                    node = node[k]
                node[path[-1]] = copy.deepcopy(rng.choice(weird))
            vc.errors.clear(); vc.warnings.clear()
            try:
                vc.validate_cfg(cfg)
            except Exception as e:  # noqa: BLE001
                self.fail(f"iteration {i}: {type(e).__name__}: {e}\nconfig: {cfg}")


if __name__ == "__main__":
    unittest.main()
