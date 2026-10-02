#!/usr/bin/env python3
"""Compile any (static-shape) ONNX model for a TI Edge AI SoC with TIDL, inside the tools container (see run_in_container.sh).

The calibration frames are run through TIDLCompilationProvider with the preprocessing the BOARD will apply, so the
quantization ranges match deployment. Calibration images must come from the training distribution, never the test set.

Preprocessing of calibration images (must mirror param.yaml / the gst pipeline):
  --hw H W              plain resize to H x W, no padding (what tiovxmultiscaler does; default style for detection/segmentation)
  --resize S --crop C   resize shorter side to S, centre-crop C x C (classification-style, as in TI zoo classifiers)
  --letterbox H W       keep aspect, pad bottom/right with 114 (only if you deploy with resize_with_pad)
  --channels bgr|rgb    channel order the MODEL expects (cv2 reads BGR; TI's param.yaml `reverse_channels: true` == model expects BGR)
  --input-dtype uint8|float32   uint8 is TI's convention: mean/scale are folded into the graph (see add_input_preprocessing.py)

Task:
  --task detection       needs --meta <prototxt> and --meta-arch-type (6 = YOLOX/YOLOv5/v7, 3 = SSD, ...)  (default)
  --task classification|segmentation    no meta architecture

--calib: text file (one image path per line) or a directory (evenly spaced images are chosen; subfolders searched).
Extra provider options: --extra key=value ...   e.g.  --extra tensor_bits=16
  --extra advanced_options:output_feature_16bit_names_list=/Conv_output_0,...   (manual mixed precision)
  --extra advanced_options:mixed_precision_factor=1.2 --accuracy-level 1 --frames 50 --iterations 50
"""
import argparse
import os
import shutil

import onnxruntime as rt

import staged_output  # same folder
import tidl_preprocess as tp  # same folder

TOOLS = os.environ["TIDL_TOOLS_PATH"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--artifacts", required=True)
    p.add_argument("--calib", required=True)
    p.add_argument("--task", choices=["detection", "classification", "segmentation"], help="default detection, or from --manifest")
    p.add_argument("--meta", help="meta-architecture prototxt (detection)")
    p.add_argument("--meta-arch-type", type=int, help="TIDL meta_arch_type (6 = YOLOX/YOLOv5/v7); default 6, or from --manifest")
    tp.add_args(p)
    p.add_argument("--frames", type=int, default=50)
    p.add_argument("--iterations", type=int, default=10)
    p.add_argument("--accuracy-level", type=int, default=1)
    p.add_argument("--tensor-bits", type=int, default=8, choices=[8, 16, 32])
    p.add_argument("--platform", default="J7", help="TIDL `platform` option; J7 was used on TDA4VM, TI lists J7 and AM62A")
    p.add_argument("--quant-scale-type", type=int, default=0, choices=[0, 1, 3, 4],
                   help="0 non-power-of-2 symmetric (default, all SoCs), 1 power-of-2, 3 TF-Lite pre-quantized, 4 asymmetric "
                        "per-channel (TI: every device except TDA4VM; not run here)")
    p.add_argument("--extra", nargs="*", default=[], help="key=value provider options")
    a = p.parse_args()
    tp.check_args(p, a)
    a.task = a.task or "detection"
    a.meta_arch_type = a.meta_arch_type or 6
    if a.manifest and a.task == "detection" and not a.meta:
        proto = tp.model_manifest.load(a.manifest).get("postprocess", {}).get("prototxt")
        if proto:
            a.meta = str(os.path.join(os.path.dirname(os.path.abspath(a.manifest)), proto))
    if a.task == "detection" and not a.meta:
        print("NOTE: detection without --meta compiles the raw network only (decode/NMS would run on ARM)")

    paths = tp.pick_images(a.calib, a.frames)   # may be fewer than --frames; the provider must be told the real count
    print(f"calibrating with {len(paths)} images ({len(set(paths))} unique; requested {a.frames})", flush=True)
    if len(paths) < a.frames:
        print(f"WARNING: only {len(paths)} calibration images available; quantization ranges come from fewer frames than "
              f"requested (TI suggests >= 50 for accuracy_level 1)", flush=True)

    # compile into a staging folder; the previous --artifacts folder survives a failed or interrupted compile
    staging = staged_output.begin(a.artifacts)
    opts = {
        "tidl_tools_path": TOOLS, "artifacts_folder": str(staging), "platform": a.platform, "version": "7.2",
        "tensor_bits": a.tensor_bits, "debug_level": 1, "max_num_subgraphs": 16, "accuracy_level": a.accuracy_level,
        "advanced_options:calibration_frames": len(paths),
        "advanced_options:calibration_iterations": a.iterations,
        "advanced_options:quantization_scale_type": a.quant_scale_type,   # 0 = symmetric (all SoCs); 4 = asymmetric per-channel, not on TDA4VM
        "advanced_options:add_data_convert_ops": 3,
        "ti_internal_nc_flag": 1601,
    }
    if a.task == "detection" and a.meta:
        opts["object_detection:meta_layers_names_list"] = a.meta
        opts["object_detection:meta_arch_type"] = a.meta_arch_type
    opts.update(dict(kv.split("=", 1) for kv in a.extra))

    try:
        sess = rt.InferenceSession(a.model, providers=["TIDLCompilationProvider", "CPUExecutionProvider"],
                                   provider_options=[opts, {}], sess_options=rt.SessionOptions())
        name = sess.get_inputs()[0].name
        for i, path in enumerate(paths):
            sess.run(None, {name: tp.preprocess(path, a)})
            print("calib", i + 1, "/", len(paths), flush=True)
        del sess                                   # the provider finishes writing the artifacts when the session is released
        if not (staging / "allowedNode.txt").is_file():
            raise RuntimeError("the compile finished without writing allowedNode.txt (no artifacts)")
    except BaseException:
        staged_output.abort(staging)
        print(f"compile failed; {a.artifacts} was left untouched", flush=True)
        raise
    previous = staged_output.commit(staging, a.artifacts)
    print(f"artifacts written to {a.artifacts}" + (f" (previous output kept at {previous})" if previous else ""), flush=True)


if __name__ == "__main__":
    main()
