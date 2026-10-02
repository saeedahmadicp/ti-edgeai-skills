#!/usr/bin/env python3
"""Preflight an ONNX model for TIDL compilation for a TI Edge AI SoC, before spending 30 minutes on a compile.

Reports, for ANY model:
  * opset / IR version, inputs and outputs (name, dtype, shape)
  * dynamic or unknown dimensions            -> ERROR  (TIDL needs static shapes: run `onnxsim` first)
  * operator census split into: listed as supported by TIDL / not listed (will run on ARM) / detection-tail ops (need a meta-architecture)
  * mid-graph Cast                           -> WARNING (TIDL supports Cast only at the network input/output)
  * SiLU/Swish pattern (x * Sigmoid(x))      -> WARNING (unbounded activation: poor int8; prefer ReLU/ReLU6/LeakyReLU)
  * Resize with unsupported mode, Conv-less graphs, no BatchNorm after convs (heuristic)

ADVISORY ONLY. The supported-op list is from edgeai-tidl-tools docs/supported_ops_rts_versions.md (tag 11_00_06_00) and is matched
by operator NAME. TI documents per-operator constraints (rank, axis, kernel/stride limits, constant operands, tensor sizes) that this
script does not check, so a listed operator can still fall back to ARM and an unlisted one may be handled by a newer tools release.
The compile log (`Subgraph Compiled Successfully`, number of subgraphs) and the board log (`Offloaded Nodes N/N`) are the authority.
Exit code 1 only on structural ERRORs (dynamic input shapes).

    python3 check_onnx_for_tidl.py model.onnx [--json]
"""
import argparse
import collections
import json
import sys

import onnx

ACCELERATED = {
    "Conv", "AveragePool", "GlobalAveragePool", "MaxPool", "Relu", "PRelu", "Sum", "Add", "Mul", "Div", "Sub", "Max",
    "Gemm", "MatMul", "Softmax", "BatchNormalization", "ConvTranspose", "Concat", "Slice", "Split", "Flatten", "Dropout",
    "ArgMax", "Upsample", "Resize", "DepthToSpace", "Sigmoid", "Pad", "ReduceMin", "ReduceMax", "ScatterND",
    "ScatterElements", "Squeeze", "Tanh", "HardSigmoid", "Elu", "Reshape", "Gather", "Transpose", "LayerNormalization",
    "GridSample", "TopK", "DeformConv", "Clip", "LeakyRelu", "Erf", "Identity", "DequantizeLinear", "QuantizeLinear",
    "Sqrt", "ReduceMean", "Pow", "Cast", "Asin", "Asinh", "HardSwish", "Mish", "Log", "Unsqueeze", "Abs", "Floor", "Exp",
    "Sin", "InstanceNormalization", "SpaceToDepth", "Acos", "Atan", "Sinh", "Neg", "Cos", "Cosh", "Tan",
}
DETECTION_TAIL = {"NonMaxSuppression", "NonZero", "GatherND", "TopK", "ConstantOfShape", "Less", "Greater", "Not", "Where",
                  "Expand", "Shape", "ReduceMax", "ArgMax", "Equal", "And", "Or"}
NEUTRAL = {"Constant"}
DTYPES = {1: "float", 2: "uint8", 3: "int8", 6: "int32", 7: "int64", 10: "float16", 9: "bool"}


def io_desc(vi):
    t = vi.type.tensor_type
    dims = [d.dim_value if d.dim_value > 0 else (d.dim_param or "?") for d in t.shape.dim]
    return {"name": vi.name, "dtype": DTYPES.get(t.elem_type, str(t.elem_type)), "shape": dims}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("onnx")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    m = onnx.load(a.onnx)
    g = m.graph
    errors, warns, info = [], [], []
    opset = max((o.version for o in m.opset_import if o.domain in ("", "ai.onnx")), default=None)
    inputs = [io_desc(i) for i in g.input if i.name not in {x.name for x in g.initializer}]
    outputs = [io_desc(o) for o in g.output]
    for i in inputs:
        if any(not isinstance(d, int) for d in i["shape"]):
            errors.append(f"input {i['name']} has dynamic/unknown dims {i['shape']}: export with fixed shapes or run onnxsim")
        if i["dtype"] not in ("uint8", "float"):
            warns.append(f"input {i['name']} dtype {i['dtype']}: TI pipeline feeds uint8 (or float)")
    ops = collections.Counter(n.op_type for n in g.node)
    arm, tail = {}, {}
    for op, c in ops.items():
        if op in ACCELERATED or op in NEUTRAL:
            continue
        (tail if op in DETECTION_TAIL else arm)[op] = c
    for op in DETECTION_TAIL & set(ops):
        if op in ACCELERATED:
            continue
    if arm:
        warns.append("operators not in TI's supported list (expected to run on ARM: slow, extra subgraph boundaries): " + ", ".join(f"{k}x{v}" for k, v in sorted(arm.items())))
    if tail:
        info.append("detection-tail ops present (" + ", ".join(f"{k}x{v}" for k, v in sorted(tail.items())) +
                    "): fine if a TIDL meta-architecture (prototxt) replaces the tail; otherwise these run on ARM")
    in_names = {i.name for i in g.input}
    out_names = {o.name for o in g.output}
    prod = {o: n for n in g.node for o in n.output}
    mid_casts = [n.name for n in g.node if n.op_type == "Cast" and n.input[0] not in in_names and n.output[0] not in out_names]
    if mid_casts:
        msg = f"{len(mid_casts)} mid-graph Cast node(s) (e.g. '{mid_casts[0]}'): TIDL supports Cast only at network input/output"
        if "NonMaxSuppression" in ops:
            info.append(msg + "; here they sit in the detection tail, which a meta-architecture replaces (TI's own zoo detectors look the same)")
        else:
            warns.append(msg + " -> they will block offload; remove them or fold into the graph")
    # SiLU: Mul(x, Sigmoid(x))
    silu = 0
    for n in g.node:
        if n.op_type == "Mul" and len(n.input) == 2:
            for k in (0, 1):
                p = prod.get(n.input[k])
                if p is not None and p.op_type == "Sigmoid" and p.input[0] == n.input[1 - k]:
                    silu += 1
    if silu:
        warns.append(f"{silu} SiLU/Swish pattern(s) (x*Sigmoid(x)): unbounded activation, poor int8 accuracy; retrain with ReLU-type activations")
    for n in g.node:
        if n.op_type in ("Resize", "Upsample"):
            mode = next((onnx.helper.get_attribute_value(x).decode() for x in n.attribute if x.name == "mode"), "nearest")
            if mode not in ("nearest", "linear"):
                warns.append(f"{n.op_type} '{n.name}' mode={mode}: TIDL supports nearest/linear only")
    nconv, nbn = ops.get("Conv", 0), ops.get("BatchNormalization", 0)
    if nconv and not nbn:
        info.append("no BatchNormalization nodes (folded into Conv at export?) - fine; if the model was trained without BN after convs, expect larger int8 loss")
    if opset is not None and opset not in (9, 11, 13):
        info.append(f"opset {opset}: TI zoo models use 11; try 11 if the importer complains")
    res = {"opset": opset, "ir_version": m.ir_version, "inputs": inputs, "outputs": outputs, "ops": dict(ops),
           "errors": errors, "warnings": warns, "info": info}
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        print(f"opset {opset}  ir {m.ir_version}  nodes {len(g.node)}")
        for i in inputs:
            print(f"  input  {i['name']}: {i['dtype']} {i['shape']}")
        for o in outputs:
            print(f"  output {o['name']}: {o['dtype']} {o['shape']}")
        print("  ops:", ", ".join(f"{k}x{v}" for k, v in sorted(ops.items())))
        for e in errors:
            print("ERROR:", e)
        for w in warns:
            print("WARNING:", w)
        for i in info:
            print("INFO:", i)
        print("no blocking errors (advisory: this check cannot prove offload)" if not errors else f"{len(errors)} error(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
