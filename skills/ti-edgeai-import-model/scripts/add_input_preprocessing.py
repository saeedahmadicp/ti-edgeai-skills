#!/usr/bin/env python3
"""Fold input normalisation into an ONNX model the way TI's zoo models do, so the board feeds raw uint8 frames.

Models trained with  y = (x - mean) * scale  on float input (typical: ImageNet mean/std) become
    uint8 input `<name>Net_IN` -> Cast(float) -> Add(-mean) -> Mul(scale) -> <original model>
using TI's own `tidlOnnxModelOptimize` (edgeai-tidl-tools/osrt-model-tools). TIDL then absorbs these nodes into the
network, so the accelerator runs the normalisation. mean/scale are per input channel, in the channel order the model
expects (0..255 pixel scale: e.g. ImageNet mean 123.675 116.28 103.53, scale 0.017125 0.017507 0.017429).

Run inside the tools container (needs onnx; TI's helper is imported from its source tree by path because the package
__init__ pulls in onnx_graphsurgeon):
    run_in_container.sh "python3 $SCRIPTS/add_input_preprocessing.py in.onnx out.onnx --mean 123.675 116.28 103.53 --scale 0.017125 0.017507 0.017429"

Do NOT use this for models that already start with a Cast from uint8 (e.g. the YOLOX export in this skill set) or that
need no normalisation: just feed uint8 directly.
"""
import argparse
import importlib.util
import os
import sys

DEFAULT_TI = "/opt/edgeai-tidl-tools/osrt-model-tools/osrt_model_tools/onnx_tools/tidl_onnx_model_utils/onnx_model_opt.py"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--mean", type=float, nargs="+", required=True, help="per channel, 0..255 scale")
    p.add_argument("--scale", type=float, nargs="+", required=True, help="per channel multiplier applied after mean subtraction")
    p.add_argument("--ti-opt", default=DEFAULT_TI, help="path to TI's onnx_model_opt.py")
    a = p.parse_args()
    if len(a.mean) != len(a.scale):
        sys.exit("--mean and --scale need the same number of channels")
    if not os.path.exists(a.ti_opt):
        sys.exit(f"{a.ti_opt} not found: run inside the tools container or pass --ti-opt")
    spec = importlib.util.spec_from_file_location("onnx_model_opt", a.ti_opt)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.tidlOnnxModelOptimize(a.src, a.dst, a.scale, a.mean)
    if not os.path.exists(a.dst):
        sys.exit("TI helper did not write the model (see 'Converted model is invalid' above)")
    print("wrote", a.dst)


if __name__ == "__main__":
    main()
