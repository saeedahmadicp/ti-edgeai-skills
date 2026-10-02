#!/usr/bin/env python3
"""COCO-evaluate a detector ONNX that outputs dets [N,5] (x1,y1,x2,y2,score) + labels [N], on CPU (float) or with TIDL host
emulation (int8), using the SAME preprocessing flags as compile_tidl.py (tidl_preprocess.py).

  python3 eval_onnx_det.py --model m_sim.onnx --data-dir <coco_dir> --split val --hw 352 640
  python3 eval_onnx_det.py ... --tidl-artifacts artifacts --tidl-tools $TIDL_TOOLS_PATH        # int8 host emulation

--data-dir layout: <split>2017/*.jpg and annotations/instances_<split>2017.json (COCO). Predicted labels are mapped to the
annotation file's category ids by sorted order (label i -> i-th category), the convention package_model.py writes.
Boxes are mapped back to the original image size for plain-resize (--hw) and letterbox (--letterbox) preprocessing.
Needs numpy, opencv, onnxruntime, pycocotools.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tidl_preprocess as tp  # noqa: E402


def make_session(args):
    if args.tidl_artifacts:
        opts = {"tidl_tools_path": args.tidl_tools or os.environ.get("TIDL_TOOLS_PATH", ""),
                "artifacts_folder": args.tidl_artifacts, "debug_level": 0}
        return ort.InferenceSession(args.model, providers=["TIDLExecutionProvider", "CPUExecutionProvider"],
                                    provider_options=[opts, {}], sess_options=ort.SessionOptions())
    return ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])


def scale_factors(args, h0, w0):
    """(sx, sy): model-input pixels per original pixel."""
    if args.letterbox:
        r = min(args.letterbox[0] / h0, args.letterbox[1] / w0)
        return r, r
    if args.hw:
        return args.hw[1] / w0, args.hw[0] / h0
    raise SystemExit("detection evaluation needs --hw or --letterbox")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--split", default="val")
    p.add_argument("--score-thr", type=float, default=0.05)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tidl-artifacts")
    p.add_argument("--tidl-tools")
    p.add_argument("--dump", type=Path, help="write detections json")
    tp.add_args(p)
    args = p.parse_args()
    tp.check_args(p, args)
    gt = COCO(str(args.data_dir / "annotations" / f"instances_{args.split}2017.json"))
    cat_ids = sorted(gt.getCatIds())
    sess = make_session(args)
    name = sess.get_inputs()[0].name
    ids = sorted(gt.getImgIds())[: args.limit or None]
    results, t0 = [], time.time()
    for i in ids:
        info = gt.loadImgs(i)[0]
        path = args.data_dir / f"{args.split}2017" / info["file_name"]
        sx, sy = scale_factors(args, info["height"], info["width"])
        dets, labels = sess.run(None, {name: tp.preprocess(path, args)})[:2]
        for (x1, y1, x2, y2, s), lab in zip(dets, np.asarray(labels).reshape(-1)):
            if s >= args.score_thr and 0 <= int(lab) < len(cat_ids):
                results.append({"image_id": i, "category_id": cat_ids[int(lab)], "score": float(s),
                                "bbox": [float(x1 / sx), float(y1 / sy), float((x2 - x1) / sx), float((y2 - y1) / sy)]})
    print(f"{len(ids)} images, {len(results)} dets, {(time.time() - t0) / len(ids) * 1000:.1f} ms/img")
    if args.dump:
        args.dump.write_text(json.dumps(results))
    if not results:
        print("no detections")
        return
    ev = COCOeval(gt, gt.loadRes(results), "bbox")
    ev.params.imgIds = ids
    ev.evaluate(); ev.accumulate(); ev.summarize()
    print("AP50:95 %.4f AP50 %.4f AR100 %.4f" % (ev.stats[0], ev.stats[1], ev.stats[8]))


if __name__ == "__main__":
    main()
