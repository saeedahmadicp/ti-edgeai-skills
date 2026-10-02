#!/usr/bin/env python3
"""Assemble a TI Edge AI model folder (model/, artifacts/, param.yaml, dataset.yaml) for ANY compiled model.

Layout expected by /opt/edgeai-gst-apps (same as /opt/model_zoo entries):

    <out>/<name>/
        model/       <onnx> [, <prototxt> for detection meta-architectures]
        artifacts/   subgraph_*_tidl_net.bin, subgraph_*_tidl_io_*.bin, allowedNode.txt, onnxrtMetaData.txt (+ layer info)
        param.yaml   preprocessing / postprocessing contract
        dataset.yaml label names

Tasks (templates taken from the TI zoo models shipped on the board):
  detection       outputs dets [N,5] (x1,y1,x2,y2,score) + labels [N]   (TIDL OD meta-architecture)
  classification  one float tensor of class scores; preprocess usually resize S + centre crop C
  segmentation    one tensor (class-index mask, uint8 when the net ends in ArgMax)

Input names, shapes and types are read from the ONNX (needs `onnx`); a dynamic INPUT dimension is an error (TIDL needs static
shapes). Detection output names come from the compile metadata (artifacts/onnxrtMetaData.txt `outDataNames`) and the box count from
the prototxt `keep_top_k` (or --max-dets); other tasks take outputs from the ONNX and refuse unknown dimensions.
Notes (see references/package-and-deploy.md):
  * list-valued preprocess resize/crop are [HEIGHT, WIDTH]; the apps reverse them internally. Ints mean square.
  * reverse_channels: true == the model expects BGR (the pipeline hands RGB to the model and flips). Use --channels rgb
    for RGB-trained models.
  * detection label_offset_pred maps model class index -> dataset category id (index i -> i+1).
"""
import argparse
import colorsys
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

DTYPES = {1: "float", 2: "uint8", 3: "int8", 6: "int32", 7: "int64", 10: "float16"}


def palette(n):
    return [[int(c * 255) for c in colorsys.hsv_to_rgb(i / max(n, 1), 0.85, 0.95)] for i in range(n)]


def onnx_io(path):
    try:
        import onnx
    except ImportError:
        return None, None

    def desc(vi):
        t = vi.type.tensor_type
        return {"name": vi.name, "shape": [d.dim_value if d.dim_value > 0 else 0 for d in t.shape.dim],  # 0 = unknown, never silently 1
                "type": f"tensor({DTYPES.get(t.elem_type, 'float')})"}
    m = onnx.load(str(path))
    return [desc(i) for i in m.graph.input], [desc(o) for o in m.graph.output]


def read_metadata(artifacts):
    """key=value lines of onnxrtMetaData.txt (written by the TIDL compile); {} when absent."""
    f = artifacts / "onnxrtMetaData.txt"
    meta = {}
    if f.is_file():
        for line in f.read_text().splitlines():
            key, sep, val = line.partition("=")
            if sep:
                meta[key.strip()] = val.strip()
    return meta


def offload_coverage(artifacts):
    """(subgraphs, accelerated_nodes, total_graph_nodes) from allowedNode.txt + onnxrtMetaData.txt, or None if the files do not
    have the expected layout (first line = subgraph count, then per subgraph a node count followed by that many node ids)."""
    f = artifacts / "allowedNode.txt"
    try:
        vals = [int(x) for x in f.read_text().split()]
        total = int(read_metadata(artifacts)["numGraphNodes"])
        n_sub, pos, accel = vals[0], 1, 0
        for _ in range(n_sub):
            cnt = vals[pos]
            pos += 1 + cnt
            accel += cnt
        return (n_sub, accel, total) if pos == len(vals) and accel <= total else None
    except (OSError, KeyError, ValueError, IndexError):
        return None


def keep_top_k(prototxt):
    m = re.search(r"keep_top_k\s*:\s*(\d+)", Path(prototxt).read_text())
    return int(m.group(1)) if m else None


def build_param(a, onnx_name, inputs, outputs, det_outputs=None):
    if a.hw:
        size = list(a.hw)
        resize, crop = size, size
    else:
        resize, crop = a.resize, a.crop
    pad = bool(a.resize_with_pad)
    det = a.task == "detection"
    if det:
        outputs = det_outputs
    param = {
        "postprocess": ({"formatter": {"dst_indices": [4, 5], "name": "DetectionBoxSL2BoxLS", "src_indices": [5, 4]},
                         "ignore_index": None, "logits_bbox_to_bbox_ls": False, "normalized_detections": False,
                         "resize_with_pad": pad, "shuffle_indices": None, "squeeze_axis": None} if det else {}),
        "preprocess": {
            "add_flip_image": False, "crop": crop, "data_layout": "NCHW",
            "pad_color": [114, 114, 114] if det else 0, "resize": resize,
            "resize_with_pad": [pad, "corner"] if det else pad, "reverse_channels": a.reverse_channels,
        },
        "session": {
            "artifacts_folder": "artifacts", "input_data_layout": "NCHW", "input_details": inputs,
            "input_mean": None, "input_optimization": True, "input_scale": None, "model_folder": "model",
            "model_path": f"model/{onnx_name}", "output_details": outputs, "run_dir": a.name,
            "session_name": "onnxrt", "target_device": a.target_device,
        },
        "task_type": a.task,
    }
    if det:
        param["metric"] = {"label_offset_pred": {i: i + 1 for i in range(len(a.classes))}}
    return param


def build_dataset(a):
    classes = a.classes or [f"class{i}" for i in range(a.num_classes or 1)]
    return {
        "info": {"description": a.description, "url": "", "version": "1.0", "year": 2025, "contributor": "",
                 "date_created": ""},
        "categories": [{"supercategory": "object", "id": i + 1, "name": n} for i, n in enumerate(classes)],
        "color_map": palette(len(classes)),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--onnx", type=Path, required=True, help="the (simplified / preprocessing-folded) ONNX that was compiled")
    p.add_argument("--prototxt", type=Path, help="meta-architecture prototxt (detection)")
    p.add_argument("--artifacts", type=Path, required=True, help="compile output dir (contains tempDir/)")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--name", required=True, help="folder name, e.g. ONR-OD-9001-mymodel-640x352 (ONR = ONNX runtime)")
    p.add_argument("--manifest", type=Path, help="model manifest (model_manifest.py): supplies task, preprocessing, classes, prototxt and "
                                                 "device; it is copied into the package with sha256 hashes of the packaged files")
    p.add_argument("--task", choices=["detection", "classification", "segmentation"], help="default detection, or from --manifest")
    p.add_argument("--hw", type=int, nargs=2, metavar=("H", "W"), help="plain resize to H W (detection / segmentation)")
    p.add_argument("--resize", type=int, help="classification: shorter-side resize")
    p.add_argument("--crop", type=int, help="classification: centre crop")
    p.add_argument("--classes", nargs="+", help="class names (detection/classification); segmentation: optional")
    p.add_argument("--num-classes", type=int, help="used when --classes is omitted")
    p.add_argument("--max-dets", type=int, help="detection: boxes per frame; default = keep_top_k from the prototxt")
    p.add_argument("--resize-with-pad", action="store_true", help="only if the pipeline letterboxes; TI's gst path does not")
    p.add_argument("--channels", choices=["bgr", "rgb"],
                   help="channel order the MODEL expects (same flag as compile_tidl.py). bgr -> reverse_channels: true "
                        "(the pipeline delivers RGB and flips it); rgb -> false. Default bgr, or from --manifest")
    p.add_argument("--target-device",
                   help="param.yaml session.target_device (TI zoo uses the product name, e.g. TDA4VM, AM68A, AM62A); default TDA4VM, or from --manifest")
    p.add_argument("--description", default="custom dataset")
    a = p.parse_args()
    manifest = None
    if a.manifest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import model_manifest
        manifest = model_manifest.load(a.manifest)
        model_manifest.apply_to_namespace(a, manifest)
        if manifest["input"].get("letterbox"):       # a letterboxing pipeline: tell post-processing to undo the padding
            a.hw, a.resize_with_pad = manifest["input"]["letterbox"], True
        if not a.prototxt and manifest.get("postprocess", {}).get("prototxt"):
            a.prototxt = a.manifest.resolve().parent / manifest["postprocess"]["prototxt"]
    a.task = a.task or "detection"
    a.channels = a.channels or "bgr"
    a.target_device = a.target_device or "TDA4VM"
    a.reverse_channels = a.channels == "bgr"
    if not a.hw and not (a.resize and a.crop):
        p.error("give --hw H W or --resize S --crop C")
    if a.task == "detection" and not a.prototxt:
        p.error("detection needs --prototxt (the meta-architecture file used at compile time)")
    if a.task == "detection" and not a.classes:
        p.error("detection needs --classes")

    inputs, outputs = onnx_io(a.onnx)
    if inputs is None:
        sys.exit("`onnx` is required to read the model's inputs/outputs: pip install onnx")
    for i in inputs:
        if any(d <= 0 for d in i["shape"]):
            sys.exit(f"input {i['name']} has dynamic/unknown dims {i['shape']}: TIDL needs static shapes (export fixed or run onnxsim)")
    meta = read_metadata(a.artifacts)
    det_outputs = None
    if a.task == "detection":
        names = meta.get("0:outDataNames", "").split(",") if meta.get("0:outDataNames") else []
        n = a.max_dets or keep_top_k(a.prototxt)
        if len(names) != 2 or not n:
            sys.exit("cannot derive the detection output contract: need artifacts/onnxrtMetaData.txt with 2 outDataNames (boxes, labels) "
                     f"and a box count (prototxt keep_top_k or --max-dets); found names={names or None}, count={n}. "
                     "Package by hand from a TI zoo param.yaml if your meta-architecture differs.")
        det_outputs = [{"name": names[0], "shape": [n, 5], "type": "tensor(float)"},
                       {"name": names[1], "shape": [n], "type": "tensor(int64)"}]
        print(f"detection outputs from compile metadata: {names[0]} [{n}, 5] (x1,y1,x2,y2,score), {names[1]} [{n}] "
              f"(box count from {'--max-dets' if a.max_dets else 'prototxt keep_top_k'})")
    else:
        for o in outputs:
            if any(d <= 0 for d in o["shape"]):
                sys.exit(f"output {o['name']} has unknown dims {o['shape']}: export static shapes (or package by hand)")
    if inputs[0]["type"] != "tensor(uint8)":
        print(f"WARNING: model input is {inputs[0]['type']}; TI's pipeline feeds uint8 with normalisation folded in "
              f"(see add_input_preprocessing.py). Continue only if you know the preprocessing path.")

    root = a.out_dir / a.name
    if root.exists():
        sys.exit(f"{root} exists; remove it or choose another --name")
    (root / "model").mkdir(parents=True)
    (root / "artifacts").mkdir()
    shutil.copy2(a.onnx, root / "model" / a.onnx.name)
    if a.prototxt:
        shutil.copy2(a.prototxt, root / "model" / (a.onnx.stem + ".prototxt"))

    for pat in ["subgraph_*_tidl_net.bin", "subgraph_*_tidl_io_*.bin", "allowedNode.txt", "onnxrtMetaData.txt"]:
        hits = list(a.artifacts.glob(pat))
        if not hits:
            sys.exit(f"missing artifact matching {pat} in {a.artifacts}: did the compile finish?")
        for f in hits:
            shutil.copy2(f, root / "artifacts" / f.name)
    for pat in ["*.layer_info.txt", "*.svg", "*_netLog.txt"]:  # optional, handy for debugging
        for f in (a.artifacts / "tempDir").glob(pat):
            shutil.copy2(f, root / "artifacts" / f.name)

    (root / "param.yaml").write_text(yaml.safe_dump(build_param(a, a.onnx.name, inputs, outputs, det_outputs), sort_keys=True))
    (root / "dataset.yaml").write_text(yaml.safe_dump(build_dataset(a), sort_keys=False))
    if manifest is not None:
        manifest["name"] = manifest["name"] or a.name
        manifest = model_manifest.seal(manifest, root)
        (root / "manifest.json").write_text(__import__("json").dumps(manifest, indent=2) + "\n")
        print(f"manifest written to {root / 'manifest.json'} with {len(manifest['files'])} file hashes "
              f"(check later with: model_manifest.py verify {root / 'manifest.json'} --root {root})")
    print(f"packaged {root}")
    nets = sorted((root / "artifacts").glob("subgraph_*_tidl_net.bin"))
    cov = offload_coverage(a.artifacts)
    if cov:
        n_sub, accel, total = cov
        print(f"offload coverage from the compile metadata: {accel}/{total} graph nodes in {n_sub} accelerator subgraph(s)"
              + ("" if accel == total else f"; {total - accel} node(s) run on ARM"))
    else:
        print(f"accelerator subgraphs: {len(nets)}; node coverage could not be read from the artifacts. A single subgraph does NOT prove "
              "full offload: check `Offloaded Nodes N/N` in the board log")
    print("confirm on the board: `Offloaded Nodes - N, Total Nodes - N` in the app log")


if __name__ == "__main__":
    main()
