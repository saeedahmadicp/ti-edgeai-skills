# Tools and how to read them

## bench_tidl.py (model-only)
Runs ONNX Runtime with `TIDLExecutionProvider` on the board. `TIDL_RT_PERFSTATS=1` is set; `--debug-level 1` prints per-layer cycle tables
(target only; host emulation prints none). Output lines start with `BENCH`. Includes everything inside `session.run`: host->C7x copy,
C7x network, device->host copy, any ARM-side ops. Excludes capture, decode, scaling, drawing, display.

## layer_cycles.py
Parses the `Layer, Layer Cycles, ...` tables (one per invocation), averages per layer, ranks, and joins names from `*.layer_info.txt`
(column 1 layerId, column 3 original node name). Typical observations (TDA4VM, YOLOX-tiny-class detector): the stem and the first head convolutions are among the top layers, and the
native detection meta layer (decode + NMS, layer name like `dets_det`) costs a fraction of a millisecond, cheaper than NMS on ARM.
- Rows arrive out of layer order (the C7x pipelines layers); only the per-layer numbers matter.
- The first invocation after session creation is slower; use `--skip-first` when you only ran a few iterations.
The other columns (`kernelOnlyCycles`, `dmaPipeupCycles`, ...) are TI-internal. TI's `tidl_osr_debug.md` describes the table.

## trace_pipeline.sh (GStreamer latency tracer)
Runs the app with `GST_TRACERS=latency(flags=element)` and TI's `parse_gst_tracers.py` (redraws every second, never exits by itself; the
wrapper stops it after 8 s and prints the last table). Columns: `latency` (time a buffer spends inside the element: this is the processing cost), `out-latency` (time between its output
buffers: pacing/throughput, ~= the frame period when the element keeps up; it is NOT processing time), `out-fps`, `frames`. A file source is paced by the decoder/encoder; a camera is paced by
its mode. Queue elements show large latency (they wait); look at processing elements (`tiovx*`, `v4l2h264enc`).
The Python app does inference outside GStreamer, so ML time is absent here; add `bench_tidl.py` ms to your estimate of end-to-end latency.

## System load (documented, not run here)
TI `perf_stats` (C++ tool in `/opt/edgeai-gst-apps/scripts/perf_stats`, README there): CPU loads (mpu1_0, c7x_1), HWA (MSC0/MSC1) load and MP/s,
DDR read/write/total bandwidth with average and peak. Build it on the board, run in a second ssh terminal during the app.
`output.overlay-perf-type: graph|text` shows similar stats on a display output (the `tiperfoverlay` GStreamer element).
`k3conf dump clock` / `k3conf set clock` inspect/change clocks (the board init script sets VPAC clocks; do not change clocks without the owner's OK).

## Host emulation timing is meaningless
x86 emulation of TIDL takes ~0.8-1.3 s per frame; use it for accuracy only.
