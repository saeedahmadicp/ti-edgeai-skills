"""Shared image preprocessing for the TI import tools: calibration, evaluation and on-board checks use ONE
implementation so quantization ranges, accuracy numbers and board outputs refer to the same input tensors.

Mirror of what the board does (param.yaml + gst pipeline):
  --hw H W              plain resize to H x W, no padding (tiovxmultiscaler)           [detection / segmentation default]
  --resize S --crop C   resize shorter side to S, centre-crop C x C                     [classification style]
  --letterbox H W       keep aspect, pad bottom/right with 114 (only for resize_with_pad pipelines)
  --channels bgr|rgb    channel order the MODEL expects (cv2 reads BGR)
  --input-dtype uint8|float32
  --manifest M          take all of the above from a model manifest (model_manifest.py); contradicting flags are an error
Needs only numpy + opencv, so it also runs on the board (copy it next to board_host_check.py).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

model_manifest = None  # set by check_args when --manifest is used
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def add_args(p):
    p.add_argument("--hw", type=int, nargs=2, metavar=("H", "W"), help="plain resize to H W")
    p.add_argument("--resize", type=int, help="classification: shorter-side resize (with --crop)")
    p.add_argument("--crop", type=int, help="classification: centre crop")
    p.add_argument("--letterbox", type=int, nargs=2, metavar=("H", "W"))
    p.add_argument("--channels", choices=["bgr", "rgb"], help="channel order the model expects (default bgr, or from --manifest)")
    p.add_argument("--input-dtype", choices=["uint8", "float32"], help="default uint8, or from --manifest")
    p.add_argument("--manifest", help="model manifest (JSON) providing preprocessing/task/classes; see model_manifest.py")


def check_args(p, a):
    if getattr(a, "manifest", None):
        global model_manifest
        import model_manifest  # same folder
        model_manifest.apply_to_namespace(a, model_manifest.load(a.manifest))
    a.channels = a.channels or "bgr"
    a.input_dtype = a.input_dtype or "uint8"
    if bool(a.crop) != bool(a.resize):
        p.error("--resize and --crop go together")
    if not (a.hw or a.crop or a.letterbox):
        p.error("give one of --hw, --resize/--crop, --letterbox")


def preprocess(path, a):
    import cv2  # imported here so the sampling helpers below work (and are testable) without OpenCV/numpy
    import numpy as np
    img = cv2.imread(str(path))
    if img is None:
        raise SystemExit(f"cannot read {path}")
    if a.crop:
        h, w = img.shape[:2]
        s = a.resize / min(h, w)
        img = cv2.resize(img, (max(a.crop, round(w * s)), max(a.crop, round(h * s))), interpolation=cv2.INTER_LINEAR)
        y, x = (img.shape[0] - a.crop) // 2, (img.shape[1] - a.crop) // 2
        img = img[y:y + a.crop, x:x + a.crop]
    elif a.letterbox:
        H, W = a.letterbox
        r = min(H / img.shape[0], W / img.shape[1])
        out = np.full((H, W, 3), 114, np.uint8)
        res = cv2.resize(img, (int(img.shape[1] * r), int(img.shape[0] * r)), interpolation=cv2.INTER_LINEAR)
        out[: res.shape[0], : res.shape[1]] = res
        img = out
    else:
        img = cv2.resize(img, (a.hw[1], a.hw[0]), interpolation=cv2.INTER_LINEAR)
    if a.channels == "rgb":
        img = img[:, :, ::-1]
    x = np.ascontiguousarray(img.transpose(2, 0, 1)[None])
    return x.astype(np.float32) if a.input_dtype == "float32" else x


def list_images(root):
    return sorted(str(f) for f in Path(root).rglob("*") if f.suffix.lower() in IMG_EXT)


def evenly_spaced(items, n):
    """n items spread evenly over the list (first and last included). With n >= len(items) all items are returned once.
    Spacing uses the number actually selected, so the picks are always distinct."""
    items = list(items)
    if n <= 0:
        raise ValueError("number of frames must be positive")
    if not items:
        raise ValueError("no items to choose from")
    n = min(n, len(items))
    if n == len(items):
        return items
    if n == 1:
        return [items[0]]
    return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]


def pick_images(calib, frames):
    """Calibration images: a text file with one path per line, or a directory (evenly spaced picks, subfolders included).
    Returns distinct paths; fewer than `frames` when fewer are available (callers must use len(result), not `frames`)."""
    if os.path.isdir(calib):
        files = list_images(calib)
        if not files:
            raise SystemExit(f"no images under {calib}")
        return evenly_spaced(files, frames)
    with open(calib) as f:
        listed = [l.strip() for l in f if l.strip()]
    if not listed:
        raise SystemExit(f"{calib} lists no images")
    missing = [p for p in listed if not os.path.isfile(p)]
    if missing:
        raise SystemExit(f"{len(missing)} listed image(s) do not exist, first: {missing[0]}")
    return evenly_spaced(list(dict.fromkeys(listed)), frames)
