#!/usr/bin/env python3
r"""Check that the board produces the same outputs as TIDL host emulation (any model type).

TI states host emulation should bit-match the device. Verify it for YOUR model before trusting host-side accuracy numbers.

  # 1) host (in the tools container):  dump outputs of the compiled model on N images
  run_in_container.sh "python3 \$SCRIPTS/board_host_check.py dump --model model.onnx --tidl-artifacts artifacts \
        --images imgs --limit 20 --out host.npz --hw 352 640"
  # 2) board:  copy this script + tidl_preprocess.py + the packaged model folder + the same images, then
  scp board_host_check.py tidl_preprocess.py root@<ip>:/tmp/ ; scp -r imgs root@<ip>:/tmp/
  ssh root@<ip> 'export PYTHONPATH=/usr/lib/python3.12/site-packages SOC=<key, e.g. j721e>; cd /tmp;
        python3 board_host_check.py dump --model /opt/model_zoo/<m>/model/<file>.onnx --tidl-artifacts /opt/model_zoo/<m>/artifacts \
        --images imgs --limit 20 --out board.npz --hw 352 640'
  scp root@<ip>:/tmp/board.npz .
  # 3) compare (anywhere with numpy):
  python3 board_host_check.py compare host.npz board.npz

This is ONE gate: runtime equivalence on IDENTICAL input tensors (this script feeds both sides with the same Python
preprocessing). It does not test the application's GStreamer preprocessing (tiovxmultiscaler/tiovxdlpreproc differ from OpenCV
resize, so TI cautions against expecting bit-exact results there) nor task accuracy; those are separate gates (see
references/package-and-deploy.md). `compare` fails on: no samples, different image lists, different preprocessing flags,
different output keys / shapes / dtypes, non-finite values, or any difference above --atol (default 0 = exact).

Use the same preprocessing flags as compile_tidl.py. Reports per output: max/mean absolute difference, and for vectors the
argmax agreement; for detection outputs (variable N) the number of detections and the max box/score difference.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tidl_preprocess as tp  # noqa: E402


def dump(a):
    import onnxruntime as ort
    opts = {"tidl_tools_path": a.tidl_tools or os.environ.get("TIDL_TOOLS_PATH", ""), "artifacts_folder": a.tidl_artifacts,
            "debug_level": 0}
    s = ort.InferenceSession(a.model, providers=["TIDLExecutionProvider", "CPUExecutionProvider"],
                             provider_options=[opts, {}], sess_options=ort.SessionOptions())
    name = s.get_inputs()[0].name
    files = tp.list_images(a.images)[: a.limit or None]
    if not files:
        sys.exit(f"no images found under {a.images}")
    outs = {}
    for i, f in enumerate(files):
        res = s.run(None, {name: tp.preprocess(f, a)})
        for k, o in enumerate(res):
            outs[f"o{k}_{i:04d}"] = np.asarray(o)
    prep = {k: getattr(a, k, None) for k in ("hw", "resize", "crop", "letterbox", "channels", "input_dtype")}
    np.savez(a.out, **outs, _files=np.array([os.path.basename(f) for f in files]), _prep=np.array(json.dumps(prep, sort_keys=True)))
    print(f"saved {len(files)} images x {len(res)} outputs to {a.out}")


def load(path):
    z = np.load(path, allow_pickle=False)
    return z, [str(f) for f in z["_files"]], str(z["_prep"]) if "_prep" in z.files else None


def compare(a):
    A, fa, pa = load(a.a)
    B, fb, pb = load(a.b)
    problems = []
    if not fa or not fb:
        problems.append("no samples in one of the files")
    if fa != fb:
        problems.append(f"different image lists ({len(fa)} vs {len(fb)} images; first differing: "
                        f"{next((x for x, y in zip(fa, fb) if x != y), 'length only')})")
    if pa != pb:
        problems.append(f"different preprocessing flags: {pa} vs {pb}")
    ka = sorted(k for k in A.files if not k.startswith("_"))
    kb = sorted(k for k in B.files if not k.startswith("_"))
    if ka != kb:
        problems.append(f"different output sets: only in A {sorted(set(ka) - set(kb))[:3]}, only in B {sorted(set(kb) - set(ka))[:3]}")
    stats = {}
    for k in sorted(set(ka) & set(kb)):
        out = k.split("_")[0]
        x, y = A[k], B[k]
        st = stats.setdefault(out, {"n": 0, "bad_shape": 0, "bad_dtype": 0, "nonfinite": 0, "max": 0.0, "sum": 0.0, "cnt": 0,
                                    "argmax_same": 0, "vec": 0})
        st["n"] += 1
        if x.dtype != y.dtype:
            st["bad_dtype"] += 1
        if x.shape != y.shape:
            st["bad_shape"] += 1
            continue
        xf, yf = x.astype(np.float64), y.astype(np.float64)
        if not (np.isfinite(xf).all() and np.isfinite(yf).all()):
            st["nonfinite"] += 1
            continue
        d = np.abs(xf - yf)
        st["max"] = max(st["max"], float(d.max()) if d.size else 0.0)
        st["sum"] += float(d.sum()); st["cnt"] += d.size
        if x.ndim <= 2 and x.size > 1 and (x.ndim == 1 or x.shape[0] == 1):
            st["vec"] += 1
            st["argmax_same"] += int(np.argmax(x) == np.argmax(y))
    print(f"policy: same {len(fa)} images, same preprocessing, same outputs/shapes/dtypes, finite values, max|diff| <= {a.atol:g}"
          f" ({'exact' if a.atol == 0 else 'tolerance'})")
    ok = not problems
    for out, st in sorted(stats.items()):
        line = (f"{out}: images {st['n']}  shape mismatches {st['bad_shape']}  dtype mismatches {st['bad_dtype']}  "
                f"non-finite {st['nonfinite']}  max|diff| {st['max']:.6g}  mean|diff| {st['sum'] / max(st['cnt'], 1):.6g}")
        if st["vec"]:
            line += f"  argmax agreement {st['argmax_same']}/{st['vec']}"
        print(line)
        ok &= st["bad_shape"] == 0 and st["bad_dtype"] == 0 and st["nonfinite"] == 0 and st["max"] <= a.atol
    for p_ in problems:
        print("PROBLEM:", p_)
    if not stats:
        ok = False
        print("PROBLEM: no comparable outputs")
    print("MATCH" if ok else "NO MATCH (see TI tidl_osr_debug.md: debug_level 3 traces, first mismatching layer)")
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--model", required=True)
    d.add_argument("--tidl-artifacts", required=True)
    d.add_argument("--tidl-tools")
    d.add_argument("--images", required=True)
    d.add_argument("--limit", type=int, default=20)
    d.add_argument("--out", required=True)
    tp.add_args(d)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--atol", type=float, default=0.0, help="max abs difference accepted (default 0: bit-exact)")
    a = p.parse_args()
    if a.cmd == "dump":
        tp.check_args(d, a)
        dump(a)
    else:
        compare(a)


if __name__ == "__main__":
    main()
