---
name: ti-edgeai-dev
description: >
  Texas Instruments Edge AI SDK development for Jacinto 7 / AM6xA processors with a C7x DSP + MMA deep-learning accelerator
  (TDA4VM, AM68A, AM69A, AM67A, AM62A): TIDL model compilation with edgeai-tidl-tools, the on-board runtime (ONNX Runtime
  with the TIDL execution provider), edgeai-gst-apps configs and tiovx* GStreamer plugins, model folders and param.yaml,
  tools-to-SDK version matching, and troubleshooting. Use this skill whenever the user mentions TIDL, C7x, MMA, TDA4VM, J721E,
  AM68A, AM69A, AM67A, AM62A, edgeai-tidl-tools, edgeai-gst-apps, /opt/model_zoo, tiovxmultiscaler, "TI edge NPU/accelerator",
  or asks how to run, deploy, debug or speed up a neural network on a TI Jacinto/Sitara board - even if they never say "skill".
  Start here, then hand off to ti-edgeai-import-model, ti-edgeai-generate-config, ti-edgeai-profile-pipeline or
  ti-edgeai-train-model.
license: MIT
metadata:
  version: 0.1.0
  tested_on: "TDA4VM (SK-TDA4VM), Edge AI SDK 11.0; other SoCs from TI documentation only (see references/platforms.md)"
---

# TI Edge AI Development

When this skill is active, **read the relevant reference document before answering or generating commands.** Option names, SoC keys
and version pairings are exact; the references hold them. Do not rely on memory.

## SDK and Architecture Quick Reference

### Components
| Where | Component | Role |
|---|---|---|
| PC (x86, Docker) | **edgeai-tidl-tools** | TIDL compile + int8 calibration, host emulation, accuracy checks |
| Board | **Edge AI SDK Linux image** | kernel, C7x firmware, TI GStreamer plugins, `/opt/model_zoo` |
| Board | **edgeai-gst-apps** (`apps_python`, optiflow, C++) | config-driven camera/video -> inference -> display/stream apps |
| Board | **ONNX Runtime + TIDL execution provider** (TFLite, TVM also exist) | runs the compiled model on the C7x/MMA; unsupported operators fall back to ARM |

Models are compiled **offline on the PC** into TIDL artifacts, then run on the board. Use a tools release that TI's compatibility table lists for the board's SDK (usually the tag of the same release line; some
releases need a firmware patch on the board).

### Typical Pipeline Flow
```
PC:    ONNX  --(TIDL compile + int8 calibration, tools release compatible with the board SDK)-->  artifacts/  --> package --> /opt/model_zoo/<model>/
Board: Source -> [Decode] -> Scaler -> DL preprocess -> Inference (ONNX RT + TIDL on C7x) -> Post-process -> Overlay -> Sink
```
| Stage | Element(s) | Notes |
|---|---|---|
| Source | `v4l2src`, `filesrc`, RTSP | camera / file / stream |
| Decode | `v4l2h264dec`, `v4l2h265dec` | hardware decoder |
| Scaler | `tiovxmultiscaler` | plain resize, **no padding**; no odd sizes |
| DL preprocess | `tiovxdlpreproc` | writes the model's input tensor from `param.yaml` |
| Inference | ONNX Runtime + TIDL (Python app) | not a GStreamer element in the Python app |
| Post-process / overlay | app code, `tiovxmosaic` | boxes, labels, mosaic of several flows |
| Sink | `kmssink` (display), `jpegenc`/`v4l2h264enc` (file), RTSP/UDP | |

### Supported SoCs
Same SDK, different names and options: `references/platforms.md` is the lookup table (tools `SOC`, gst-apps `SOC`, quantization,
`--target-device`). Identify the SoC from the board before choosing values.

## Critical Rules

1. **Select a tools release that is compatible with the board's SDK.** Read the SDK on the board (`env | grep -i -E "EDGEAI|SDK"`),
   look up the SoC's column of edgeai-tidl-tools `docs/version_compatibility_table.md` (`references/sdk-versions.md`), and prefer
   the same release line. TI also lists older-SDK compatibility for some tags, but those rows need a firmware update on the target.
   Check compiled artifacts with `ti-edgeai-import-model/scripts/check_artifacts_version.py`: an incompatible artifact compiles
   fine and only fails on the board (`TIVX_CMD_NODE_CREATE failed`).
2. **Export the gst-apps SoC key before running `app_edgeai.py`** (`export SOC=<key>`, `references/platforms.md`). Without it the
   app silently builds an ARM-only pipeline (plain `videoscale`, no `tiovx*`): much slower and different preprocessing.
3. **TI's GStreamer path resizes without padding.** `tiovxmultiscaler` squashes the frame to the model input size. Export the model
   near the camera aspect (e.g. 640x352 for 16:9) and train/calibrate with the same plain resize, otherwise boxes are stretched.
4. **List-valued `resize`/`crop` in `param.yaml` are `[height, width]`.** The app reverses them; the wrong order shows as
   `Got invalid dimensions for input`.
5. **Check which quantization the SoC supports.** TDA4VM is symmetric int8 only; others also support asymmetric per-channel
   (`references/platforms.md`). Default int8 PTQ costs a few AP points on detectors; mixed precision or QAT are the levers.
6. **Static shapes, simplified graph.** Run `onnxsim` before compiling; otherwise the importer reports
   `Unknown input dimension, not supported by TIDL` for every layer.
7. **Detection post-processing belongs in TIDL** (`object_detection:meta_arch_type` + a prototxt): decode + NMS run on the C7x and
   the model returns `dets`/`labels` like TI's zoo models.
8. **The TIDL import tool needs shared memory.** Docker's 64 MB default gives `Bus error`; run with `--shm-size=4g`.
9. **Display runs need the stock GUI stopped** (`edgeai-init.service`) and the app run as a systemd unit, because background
   children of an ssh session are killed at logout. Stopping the GUI is a board-state change: get authorization first, record the
   original state, restore it afterwards (`ti-edgeai-generate-config`, `references/board-and-services.md`).
10. **Prove offload.** "Runs on the accelerator" means: compile log `Subgraph Compiled Successfully`, board log
    `Offloaded Nodes - N, Total Nodes - N`, no `VX_ZONE_ERROR`. State exactly which of these you saw.
11. **Authorization comes before any board-state change**: services, firmware updates, reboots, USB/driver resets, clock changes.
    Ask, wait for an explicit yes, record the original state, give restoration steps. Copying a new model folder under
    `/opt/model_zoo` is fine, but never overwrite or delete an existing one (`deploy_to_board.sh` refuses without `REPLACE=1`).

## Key Paths on the Board

| Path | What |
|---|---|
| `/opt/edgeai-gst-apps/apps_python/app_edgeai.py` | Python app (configs in `../configs/*.yaml`) |
| `/opt/edgeai-gst-apps/optiflow/` | OpTIFlow: pure-GStreamer variant (no app code) |
| `/opt/edgeai-gst-apps/configs/{app_config_template,gst_plugins_map}.yaml` | full option list; SoC -> plugin map |
| `/opt/model_zoo/<model>/{model,artifacts,param.yaml,dataset.yaml}` | deployable models |
| `/opt/edgeai-test-data/{images,videos,output}` | sample inputs / default output dir |
| `/opt/vx_app_arm_remote_log.out` | C7x/MCU remote log reader (`/opt/vision_apps/vision_apps_init.sh`) |
| `k3conf`, `/opt/edgeai-gst-apps/scripts/{perf_stats,gst_tracers}` | clocks, load, per-element latency |

## Reference Documents

**IMPORTANT**: read the one that matches the task.

| File | Use when |
|---|---|
| [references/platforms.md](references/platforms.md) | choosing SoC-dependent values: tools SOC, gst SOC, quantization, target device |
| [references/sdk-versions.md](references/sdk-versions.md) | choosing/verifying the tools tag, firmware patch notes, version stamp |
| [references/board-and-services.md](references/board-and-services.md) | board access, services, display, cameras, logs |
| [references/gst-apps-and-plugins.md](references/gst-apps-and-plugins.md) | app config schema, pipeline anatomy, tiovx plugins, model folder contract |
| [references/tidl-ops-and-limits.md](references/tidl-ops-and-limits.md) | which ONNX ops run on C7x, meta-architectures, quantization options |
| [references/troubleshooting.md](references/troubleshooting.md) | longer symptom -> cause -> fix list, debug-level recipes |
| [references/sources.md](references/sources.md) | TI documentation links, and what has been run vs only read |

## Quick Error Reference

| Symptom | Cause -> fix |
|---|---|
| `TIVX_CMD_NODE_CREATE failed ... Create state function failed` | artifact/firmware version mismatch -> rebuild with the matching tools tag |
| `Got invalid dimensions for input: images ... Expected: 352` | param.yaml resize/crop order -> `[H, W]` |
| `SOC env var not specified. Defaulting target to arm` | forgot `export SOC=<key>` |
| `Flow output resolution can not be greater than input resolution` | config output size > input size |
| `setupterm: could not find terminal` / `cbreak() returned ERR` | the status screen needs a tty: `TERM=xterm`, or `script`/`systemd-run` |
| Compile: `Unknown input dimension` | run onnxsim / shape inference first |
| Compile: `Bus error`, `libcgraph.so.6` missing | `--shm-size=4g`, install graphviz in the image |
| No `/dev/video*` camera after boot, `usbN-portM: Cannot enable` | USB hub failed at boot: power-cycle with the camera attached |
| Boxes stretched/offset, no errors | ARM-only pipeline (no `SOC`) or letterbox-trained model on a squashing pipeline |

More in `references/troubleshooting.md`.
