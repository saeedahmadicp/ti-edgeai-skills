#!/usr/bin/env python3
"""Model manifest: ONE file that carries a model's deployment contract between the training, import, configuration and profiling steps,
so preprocessing, classes, thresholds and toolchain versions are written down once instead of repeated as command-line flags.

    model_manifest.py init   --out m.json --name mymodel --task detection --hw 352 640 --channels bgr --classes a b \
                             --prototxt m.prototxt --meta-arch-type 6 --viz-threshold 0.3 --tools-soc am68pa --tidl-tag 11_00_06_00 \
                             --device TDA4VM
    model_manifest.py validate m.json                    # schema check, exit 1 on problems
    model_manifest.py seal   m.json --root pkg/mymodel   # record sha256 of every file under model/, artifacts/, param.yaml, dataset.yaml
    model_manifest.py verify m.json --root pkg/mymodel   # recompute and compare (exit 1 on a mismatch, missing OR extra file)

Consumers: compile_tidl.py, eval_onnx_det.py, eval_classification.py, board_host_check.py and package_model.py accept `--manifest m.json`
and take preprocessing / task / classes / target from it (explicit flags that contradict the manifest are an error). JSON only, stdlib only.

Schema (schema_version 1)
  name, task: detection|classification|segmentation
  input:  one of {hw:[H,W]} | {resize:S, crop:C} | {letterbox:[H,W]}; channels: bgr|rgb (what the MODEL expects); dtype: uint8|float32
  classes: [names]                                  (detection/classification)
  postprocess: {meta_arch_type, prototxt, viz_threshold}    (all optional)
  target: {tools_soc, tidl_tag, device, board_sdk}          (all optional strings)
  files:  {relative/path: sha256}                           (written by `seal`)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

TASKS = ("detection", "classification", "segmentation")
SCHEMA = 1


def _pair(v):
    return isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in v)


def _posint(v):
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def validate(m):
    errs = []
    if not isinstance(m, dict):
        return ["manifest must be a JSON object"]
    if m.get("schema_version") != SCHEMA:
        errs.append(f"schema_version must be {SCHEMA}")
    if not isinstance(m.get("name"), str) or not m.get("name"):
        errs.append("name: non-empty string required")
    task = m.get("task")
    if task not in TASKS:
        errs.append(f"task must be one of {TASKS}")
    inp = m.get("input")
    if not isinstance(inp, dict):
        errs.append("input: object required")
    else:
        modes = [k for k in ("hw", "letterbox") if k in inp] + (["resize+crop"] if "resize" in inp or "crop" in inp else [])
        if len(modes) != 1:
            errs.append("input: give exactly one of hw, letterbox, or resize+crop")
        for k in ("hw", "letterbox"):
            if k in inp and not _pair(inp[k]):
                errs.append(f"input.{k}: [height, width] positive integers required")
        if "resize" in inp or "crop" in inp:
            if not (_posint(inp.get("resize")) and _posint(inp.get("crop"))):
                errs.append("input.resize and input.crop: positive integers required together")
        if inp.get("channels") not in ("bgr", "rgb"):
            errs.append("input.channels: bgr or rgb required (the order the MODEL expects)")
        if inp.get("dtype", "uint8") not in ("uint8", "float32"):
            errs.append("input.dtype: uint8 or float32")
    classes = m.get("classes")
    if task in ("detection", "classification"):
        if not (isinstance(classes, list) and classes and all(isinstance(c, str) and c for c in classes) and len(set(classes)) == len(classes)):
            errs.append("classes: non-empty list of unique names required for detection/classification")
    post = m.get("postprocess", {})
    if not isinstance(post, dict):
        errs.append("postprocess: object")
    else:
        t = post.get("viz_threshold")
        if t is not None and not (isinstance(t, (int, float)) and not isinstance(t, bool) and 0 <= t <= 1):
            errs.append("postprocess.viz_threshold: number in [0, 1]")
        if "meta_arch_type" in post and not _posint(post["meta_arch_type"]):
            errs.append("postprocess.meta_arch_type: positive integer")
        if task == "detection" and "prototxt" not in post:
            errs.append("postprocess.prototxt: detection needs the meta-architecture prototxt name")
    tgt = m.get("target", {})
    if not isinstance(tgt, dict) or any(not isinstance(v, str) for v in tgt.values()):
        errs.append("target: object of strings (tools_soc, tidl_tag, device, board_sdk)")
    files = m.get("files", {})
    if not isinstance(files, dict) or any(not isinstance(v, str) or len(v) != 64 for v in files.values()):
        errs.append("files: {path: sha256 hex}")
    return errs


def load(path):
    try:
        m = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"cannot read manifest {path}: {e}")
    errs = validate(m)
    if errs:
        raise SystemExit(f"invalid manifest {path}:\n  - " + "\n  - ".join(errs))
    return m


def to_args(m):
    """manifest -> flat dict using the option names of the tools (hw, resize, crop, letterbox, channels, input_dtype, task, ...)."""
    inp, post, tgt = m["input"], m.get("postprocess", {}), m.get("target", {})
    return {k: v for k, v in {
        "hw": inp.get("hw"), "resize": inp.get("resize"), "crop": inp.get("crop"), "letterbox": inp.get("letterbox"),
        "channels": inp["channels"], "input_dtype": inp.get("dtype", "uint8"), "task": m["task"], "classes": m.get("classes"),
        "meta_arch_type": post.get("meta_arch_type"), "viz_threshold": post.get("viz_threshold"),
        "target_device": tgt.get("device"),
    }.items() if v is not None}


def apply_to_namespace(a, m):
    """Fill options the user left unset from the manifest; an explicit option that contradicts it is an error."""
    conflicts = []
    for k, v in to_args(m).items():
        if not hasattr(a, k):
            continue
        cur = getattr(a, k)
        if cur in (None, [], False):
            setattr(a, k, v)
        elif list(cur) != list(v) if isinstance(v, list) else cur != v:
            conflicts.append(f"--{k.replace('_', '-')} {cur} contradicts the manifest ({v})")
    # preprocessing modes are mutually exclusive: if the manifest chose one, a flag for another mode is a contradiction too
    chosen = [k for k in ("hw", "letterbox") if m["input"].get(k)] or (["crop"] if m["input"].get("crop") else [])
    for k in ("hw", "letterbox", "crop"):
        if hasattr(a, k) and getattr(a, k) and k not in chosen and chosen:
            conflicts.append(f"--{k.replace('_', '-')} given but the manifest uses {chosen[0]}")
    if conflicts:
        raise SystemExit("flags disagree with the manifest:\n  - " + "\n  - ".join(conflicts))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sealed_files(root):
    root = Path(root)
    out = []
    for sub in ("model", "artifacts"):
        out += sorted(p for p in (root / sub).rglob("*") if p.is_file())
    out += [p for p in (root / "param.yaml", root / "dataset.yaml") if p.is_file()]
    return out


def seal(m, root):
    root = Path(root)
    files = sealed_files(root)
    if not files:
        raise SystemExit(f"no files to seal under {root} (expected model/, artifacts/, param.yaml)")
    m["files"] = {str(p.relative_to(root)): sha256(p) for p in files}
    return m


def verify(m, root):
    root = Path(root)
    problems = []
    for rel, digest in m.get("files", {}).items():
        p = root / rel
        if not p.is_file():
            problems.append(f"missing: {rel}")
        elif sha256(p) != digest:
            problems.append(f"changed: {rel}")
    if not m.get("files"):
        problems.append("manifest has no file hashes (run `seal`)")
    else:  # the managed set must match exactly: a file added after sealing is a change too
        listed = set(m["files"])
        for p in sealed_files(root):
            rel = str(p.relative_to(root))
            if rel not in listed:
                problems.append(f"unlisted file (added after sealing): {rel}")
    return problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--out", required=True)
    i.add_argument("--name", required=True)
    i.add_argument("--task", choices=TASKS, required=True)
    i.add_argument("--hw", type=int, nargs=2, metavar=("H", "W"))
    i.add_argument("--letterbox", type=int, nargs=2, metavar=("H", "W"))
    i.add_argument("--resize", type=int)
    i.add_argument("--crop", type=int)
    i.add_argument("--channels", choices=["bgr", "rgb"], required=True)
    i.add_argument("--input-dtype", choices=["uint8", "float32"], default="uint8")
    i.add_argument("--classes", nargs="+")
    i.add_argument("--prototxt")
    i.add_argument("--meta-arch-type", type=int)
    i.add_argument("--viz-threshold", type=float)
    i.add_argument("--tools-soc")
    i.add_argument("--tidl-tag")
    i.add_argument("--device")
    i.add_argument("--board-sdk")
    v = sub.add_parser("validate"); v.add_argument("manifest")
    s = sub.add_parser("seal"); s.add_argument("manifest"); s.add_argument("--root", required=True)
    c = sub.add_parser("verify"); c.add_argument("manifest"); c.add_argument("--root", required=True)
    a = p.parse_args()
    if a.cmd == "init":
        inp = {"channels": a.channels, "dtype": a.input_dtype}
        for k in ("hw", "letterbox", "resize", "crop"):
            if getattr(a, k):
                inp[k] = list(getattr(a, k)) if isinstance(getattr(a, k), (list, tuple)) else getattr(a, k)
        post = {k: v for k, v in (("prototxt", a.prototxt), ("meta_arch_type", a.meta_arch_type),
                                  ("viz_threshold", a.viz_threshold)) if v is not None}
        tgt = {k: v for k, v in (("tools_soc", a.tools_soc), ("tidl_tag", a.tidl_tag), ("device", a.device),
                                 ("board_sdk", a.board_sdk)) if v}
        m = {"schema_version": SCHEMA, "name": a.name, "task": a.task, "input": inp, "classes": a.classes,
             "postprocess": post, "target": tgt}
        m = {k: v for k, v in m.items() if v is not None}
        errs = validate(m)
        if errs:
            sys.exit("not written:\n  - " + "\n  - ".join(errs))
        Path(a.out).write_text(json.dumps(m, indent=2) + "\n")
        print(f"wrote {a.out}")
    elif a.cmd == "validate":
        m = load(a.manifest)
        print(f"OK: {m['name']} ({m['task']})")
    elif a.cmd == "seal":
        m = seal(load(a.manifest), a.root)
        Path(a.manifest).write_text(json.dumps(m, indent=2) + "\n")
        print(f"sealed {len(m['files'])} files into {a.manifest}")
    else:
        problems = verify(load(a.manifest), a.root)
        for x in problems:
            print("PROBLEM:", x)
        print("VERIFIED" if not problems else f"{len(problems)} problem(s)")
        sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
