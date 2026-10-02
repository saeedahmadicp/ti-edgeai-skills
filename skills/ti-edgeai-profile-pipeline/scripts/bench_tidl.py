#!/usr/bin/env python3
"""Time a compiled TIDL model on a TI Edge AI board's C7x with ONNX Runtime (run ON THE BOARD).

    export PYTHONPATH=/usr/lib/python3.12/site-packages SOC=<gst-apps SoC key, e.g. j721e>
    python3 bench_tidl.py /opt/model_zoo/<model-folder> [--runs 200] [--debug-level 1]

Reads the model folder layout (model/*.onnx, artifacts/), builds a session with TIDLExecutionProvider, feeds random
data of the right shape/dtype and reports end-to-end ms per frame for session.run() (host->C7x->host + any ARM-side ops).
It excludes capture, decode, scaling and display, so it is the *model* number, not the pipeline FPS.
--debug-level 1 makes TIDL print per-layer C7x cycles (on target only); pipe stdout to layer_cycles.py to rank layers.
"""
import argparse
import os
import time

import numpy as np
import onnxruntime as rt

p = argparse.ArgumentParser()
p.add_argument("model_dir")
p.add_argument("--runs", type=int, default=200)
p.add_argument("--warmup", type=int, default=10)
p.add_argument("--debug-level", type=int, default=0)
a = p.parse_args()

os.environ["TIDL_RT_PERFSTATS"] = "1"
onnx = os.path.join(a.model_dir, "model", next(f for f in os.listdir(os.path.join(a.model_dir, "model")) if f.endswith(".onnx")))
s = rt.InferenceSession(onnx, providers=["TIDLExecutionProvider", "CPUExecutionProvider"],
                        provider_options=[{"artifacts_folder": os.path.join(a.model_dir, "artifacts"),
                                           "debug_level": a.debug_level}, {}], sess_options=rt.SessionOptions())
inp = s.get_inputs()[0]
dtype = {"tensor(uint8)": np.uint8, "tensor(float)": np.float32}[inp.type]
shape = [d if isinstance(d, int) else 1 for d in inp.shape]
x = (np.random.randint(0, 255, shape).astype(dtype) if dtype == np.uint8 else np.random.rand(*shape).astype(dtype))
for _ in range(a.warmup):
    s.run(None, {inp.name: x})
ts = []
for _ in range(a.runs):
    t = time.perf_counter()
    out = s.run(None, {inp.name: x})
    ts.append((time.perf_counter() - t) * 1000)
ts = np.array(ts)
print(f"BENCH input={inp.name}{shape}:{inp.type} outputs={[tuple(o.shape) for o in out]}")
print(f"BENCH ms/frame mean={ts.mean():.2f} p50={np.percentile(ts, 50):.2f} p95={np.percentile(ts, 95):.2f} "
      f"min={ts.min():.2f} max={ts.max():.2f}  => {1000 / ts.mean():.1f} fps (model only)")
