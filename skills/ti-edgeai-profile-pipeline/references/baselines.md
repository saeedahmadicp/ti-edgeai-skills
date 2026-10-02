# Measured baselines (SK-TDA4VM, Edge AI SDK 11.0, int8, `bench_tidl.py`, 100-200 runs, model-only)

Use these to sanity-check your own numbers and to estimate whether a model fits a frame budget.

| Model (TI zoo unless noted) | Task | Input | ms / frame (mean) | fps ceiling |
|---|---|---|---|---|
| RegNetX-200MF | classification | 1x3x224x224 | 2.92 | 342 |
| YOLOX-nano-lite (COCO) | detection, OD meta layer | 416x416 | 4.64 | 216 |
| DeepLabV3+ MobileNetV2 lite (ADE20K) | segmentation, ArgMax in net | 512x512 | 7.30 | 137 |
| YOLOX-s-lite (COCO) | detection, OD meta layer | 640x640 | 11.66 | 86 |

Spread is tight (p95 within ~0.05 ms of p50). Numbers are `session.run` including host<->C7x copies and any ARM-side ops.

## Other measurements
| Item | Result | Tool |
|---|---|---|
| C7x layer-cycle sum, RegNetX-200MF | 2.29 ms over 62 layers; top layer 24% of cycles | same |
| 30 fps H.264 1280x768 file -> detector (YOLOX-tiny class) -> H.264 mkv (Python app) | held 30 fps; `tiovxdlpreproc` ~1.8 ms, colorconvert 3.3-5.1 ms, H.264 encode 10.8-14 ms | `trace_pipeline.sh` |
| USB webcam 640x360@30 -> detector -> jpg files | ~660 frames in 25 s (~26-30 fps incl. start-up and JPEG writes) | frame count |
| Host x86 TIDL emulation | ~0.8-1.3 s per detector frame | `eval_onnx_det.py` |

Not measured: power, DDR bandwidth/loads (`perf_stats`), display-sink FPS, CSI camera, several simultaneous models.
