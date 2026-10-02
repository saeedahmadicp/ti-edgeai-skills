#!/usr/bin/env python3
"""Evaluate a classification ONNX (CPU float, or TIDL host emulation / on the board) on a folder of images.

  python3 eval_classification.py --model m.onnx --images val_dir --resize 256 --crop 224 --channels rgb \
      [--tidl-artifacts artifacts --tidl-tools $TIDL_TOOLS_PATH] [--reference-onnx float_model.onnx]

--images: either `root/<class_name>/*.jpg` (labels = sorted sub-folder index; reports top-1/top-5 accuracy) or a flat folder
(no labels). With --reference-onnx the script also reports how often TIDL's top-1 agrees with the float model's and the mean
cosine similarity of the output vectors: a label-free measure of quantization damage that works for any classifier.
Preprocessing flags are shared with compile_tidl.py (tidl_preprocess.py): use the SAME values you compiled with.
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tidl_preprocess as tp  # noqa: E402


def session(model, art=None, tools=None):
    if art:
        return ort.InferenceSession(model, providers=["TIDLExecutionProvider", "CPUExecutionProvider"],
                                    provider_options=[{"tidl_tools_path": tools or os.environ.get("TIDL_TOOLS_PATH", ""),
                                                       "artifacts_folder": art, "debug_level": 0}, {}],
                                    sess_options=ort.SessionOptions())
    return ort.InferenceSession(model, providers=["CPUExecutionProvider"])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--images", type=Path, required=True)
    p.add_argument("--tidl-artifacts")
    p.add_argument("--tidl-tools")
    p.add_argument("--reference-onnx")
    p.add_argument("--limit", type=int, default=0)
    tp.add_args(p)
    a = p.parse_args()
    tp.check_args(p, a)

    sub = sorted(d for d in a.images.iterdir() if d.is_dir())
    labelled = bool(sub) and all(any(Path(d).rglob("*")) for d in sub)
    classes = [d.name for d in sub] if labelled else []
    files = [(f, classes.index(Path(f).parent.name) if labelled else -1) for f in tp.list_images(a.images)]
    if a.limit:
        files = files[: a.limit]
    s = session(a.model, a.tidl_artifacts, a.tidl_tools)
    r = session(a.reference_onnx) if a.reference_onnx else None
    name = s.get_inputs()[0].name
    top1 = top5 = agree = 0
    cos = []
    for f, y in files:
        x = tp.preprocess(f, a)
        out = np.asarray(s.run(None, {name: x})[0]).reshape(-1).astype(np.float64)
        order = np.argsort(-out)
        if labelled:
            top1 += int(order[0] == y)
            top5 += int(y in order[:5])
        if r is not None:
            ref = np.asarray(r.run(None, {r.get_inputs()[0].name: x})[0]).reshape(-1).astype(np.float64)
            agree += int(order[0] == np.argmax(ref))
            cos.append(float(out @ ref / (np.linalg.norm(out) * np.linalg.norm(ref) + 1e-12)))
    n = len(files)
    print(f"{n} images, {len(classes) or 'unlabelled'} classes")
    if labelled:
        print(f"top-1 {top1 / n:.4f}  top-5 {top5 / n:.4f}")
    if r is not None:
        print(f"top-1 agreement with reference {agree / n:.4f}  mean cosine {np.mean(cos):.5f}")


if __name__ == "__main__":
    main()
