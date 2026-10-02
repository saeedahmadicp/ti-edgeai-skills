---
name: ti-edgeai-profile-pipeline
description: >
  Measure and improve inference speed on TI Edge AI boards with a C7x/MMA accelerator (TDA4VM, AM68A, AM69A, AM67A, AM62A):
  model-only latency, per-layer C7x cycle hotspots, per-element GStreamer latency and FPS of the edgeai-gst-apps pipeline,
  system load, and the levers that trade accuracy for speed (input size, 16-bit layers, frame rate, output size). Use this
  skill whenever the user asks how fast a model runs on the TI board, wants FPS, latency, "why is it slow", per-layer
  timings, which stage is the bottleneck, whether the pipeline can keep 30 fps, or how much a precision/size change costs -
  even if they only say "benchmark it on the TI device".
license: MIT
metadata:
  version: 0.1.0
  tested_on: "TDA4VM, Edge AI SDK 11.0: classification, segmentation and detection models; other SoCs untested"
---

# Profile a Model and Pipeline on TI Edge AI

When this skill is active, **separate the questions**: each has its own tool and a different number. Read
`references/perf-tools.md` before interpreting output.

| Question | Tool | Reports |
|---|---|---|
| How long does the **model** take? | `scripts/bench_tidl.py` | ms per `session.run` (C7x + any ARM-side ops), fps ceiling |
| Which **layers** dominate? | `bench_tidl.py --debug-level 1` + `scripts/layer_cycles.py` | C7x cycles per layer, % of total |
| Does the **pipeline** keep up (decode, scale, preproc, encode)? | `scripts/trace_pipeline.sh` | latency and FPS per GStreamer element |
| Is the **system** saturated (C7x, HWA, DDR)? | `perf_stats` (compile first) / `top` / `k3conf` | loads, DDR bandwidth |

Never quote model-only ms as application FPS, and never quote pipeline FPS without saying whether the source was a camera
(rate-limited) or a file. State both numbers when you have them. Numbers are specific to the SoC and clock: never reuse another
SoC's figures (`ti-edgeai-dev/references/platforms.md`).

## Procedure

0. **Preconditions**: the board is idle (no demo unit, no other C7x user). On the board export `SOC=<GST_SOC>` and
   `PYTHONPATH=/usr/lib/python3.12/site-packages` (path depends on the image's Python) for the Python scripts.
1. **Model time** (on the board):
   ```bash
   scp scripts/bench_tidl.py root@<board-ip>:/tmp/ && ssh root@<board-ip> 'export PYTHONPATH=/usr/lib/python3.12/site-packages SOC=<GST_SOC>;
       python3 /tmp/bench_tidl.py /opt/model_zoo/<model> --runs 200 | grep BENCH'
   ```
   It reads dtype/shape from the ONNX, warms up, and prints mean/p50/p95/min/max. A tight spread is expected on a quiet board.
2. **Layers**: `bench_tidl.py <model> --runs 20 --debug-level 1 > dbg.log 2>&1` on the board, copy `dbg.log` back, then
   `python3 scripts/layer_cycles.py dbg.log --layer-info <model>/artifacts/*.layer_info.txt --top 15 --skip-first`.
   Convert cycles with the C7x clock (`k3conf`; 1 GHz on TDA4VM: ms = cycles / 1e6). The sum of layer cycles is the C7x busy time;
   the gap to the session time is ARM-side handling and data movement.
3. **Pipeline**: `BOARD=root@<board-ip> GST_SOC=<key> scripts/trace_pipeline.sh ../configs/<config>.yaml 25` (finite or file input,
   file/fakesink output). Read two different things: `latency` is the processing cost inside an element (sum it along the
   chain and compare with the frame period), while `out-fps`/`out-latency` show pacing: the first element whose `out-fps` falls below
   the source rate is where throughput is lost, but the cost sits in that element's `latency` or its downstream queue. Do not call
   `out-latency` a processing time. Inference is not in this table in the Python app (it runs outside GStreamer).
4. **Interpret** with `references/perf-tools.md`, choose levers from `references/optimization-levers.md`. Change one lever at a
   time, re-measure, and record accuracy next to speed (`ti-edgeai-import-model` for the accuracy side).

## Reference Documents
| File | Use when |
|---|---|
| [references/perf-tools.md](references/perf-tools.md) | reading bench / tracer / perf_stats output |
| [references/optimization-levers.md](references/optimization-levers.md) | what to change when a number is too high |
| [references/baselines.md](references/baselines.md) | reference timings of TI zoo models (TDA4VM) to sanity-check yours |

## Reporting format
```
Model <name> HxW on <SoC>: session ms mean/p95 (fps ceiling) | C7x layer-cycle sum ms | top-5 layers
Pipeline <config>: source type, achieved fps, slowest elements (ms)
Levers tried: <change> -> <ms/fps> / <accuracy>      Measured: ...      Not run: ...
```
