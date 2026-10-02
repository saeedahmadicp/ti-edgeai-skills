---
name: ti-edgeai-import-model
description: >
  Get a trained neural network that exports to a static-shape ONNX (a classifier, a segmentation model, or a detector with a
  TIDL meta-architecture such as YOLOX/SSD/YOLOv5-style) running on a TI Edge AI board's C7x/MMA accelerator
  (TDA4VM, AM68A, AM69A, AM67A, AM62A): preflight the ONNX, fold input normalisation, compile and int8-calibrate with
  edgeai-tidl-tools in Docker (tools tag matched to the board SDK), verify offload and accuracy in host emulation, check
  board-vs-host outputs, package model/ artifacts/ param.yaml dataset.yaml, deploy to /opt/model_zoo and smoke-test with
  edgeai-gst-apps. Use this skill whenever the user wants to deploy, convert, compile, quantize, port or "put my model on" a
  TI Jacinto/AM6xA board, mentions TIDL compilation, artifacts, tidl_net.bin, meta_arch_type, a prototxt, calibration images,
  int8 accuracy loss on the TI device, or asks why a compiled model fails on the board - for any architecture within those contracts,
  and even if they only say "deploy to the TI device".
license: MIT
metadata:
  version: 0.1.0
  tested_on: "TDA4VM, Edge AI SDK 11.0: a YOLOX-tiny TI-lite detector and a float-input classifier through the full flow; other SoCs untested"
---

# Import a Model into TI Edge AI

When this skill is active, **read the reference named in each phase before running it.** **Scope**: a model whose ONNX export has static input shapes and mostly supported operators, in one of three task contracts
(below). Out of scope: dynamic shapes (export fixed ones), operators TIDL cannot run (they fall back to ARM or block offload),
models with several inputs or non-image inputs (not tested), and TFLite/TVM flows. The three task types share one flow and differ
only in the compile options and `param.yaml`:

| Task | Compile extras | Output the board app expects | Run end to end |
|---|---|---|---|
| detection with a TIDL meta-architecture (YOLOX/YOLOv5/7 type 6, SSD 3, YOLOv3 4, RetinaNet 5, YOLOv8 8) | `--meta <prototxt> --meta-arch-type N` | `dets [N,5]` + `labels [N]` | YOLOX type 6 (TDA4VM) |
| classification | none | one score vector | float-input CNN with folded mean/scale (TDA4VM) |
| segmentation | none | class-index mask (uint8 if the net ends in ArgMax) | no (param.yaml template from the TI zoo only) |

Read `ti-edgeai-dev` first if new to the platform; it holds the rules this flow depends on (tools release compatible with the board SDK, gst-apps
`SOC` key, `[H, W]` order, no-padding resize). SoC-dependent values (tools SOC, `--target-device`, quantization): `ti-edgeai-dev/references/platforms.md`. **Report evidence at each gate**: a phase is done when its check passed, not when the
command returned.

## One manifest instead of repeated flags
Write `model_manifest.py init` once (task, input policy, channel order, classes, meta-architecture, SoC and tools tag) and pass
`--manifest` to compile, evaluators, `board_host_check.py` and `package_model.py`; contradicting flags are an error and packaging
seals file hashes (`references/model-manifest.md`). Flags still work without a manifest.

## Phases and gates

| # | Phase | Script / reference | Gate |
|---|---|---|---|
| 0 | Pre-flight: board SDK -> tools tag, tools container | `references/compile-tidl.md` | tag chosen from the compatibility table; image exists |
| 1 | Get a TIDL-friendly ONNX | `check_onnx_for_tidl.py`, `add_input_preprocessing.py`, `references/export-onnx-for-tidl.md` | no ERRORs; input uint8 (normalisation folded); ONNX matches the framework model |
| 2 | Compile + calibrate | `compile_tidl.py` (in container) | `Subgraph Compiled Successfully`; subgraph count and offload as expected |
| 3 | Verify artifacts + accuracy | `check_artifacts_version.py`, `eval_onnx_det.py` / `eval_classification.py` | stamp OK; int8 within tolerance of float |
| 4 | Package | `package_model.py` | param.yaml matches the task contract |
| 5 | Deploy + smoke test + numerics | `deploy_to_board.sh`, `board_host_check.py` | app exit 0, `Offloaded Nodes N/N`, board == host outputs |
| 6 | Accuracy / speed loop | `references/quantization-accuracy.md`, `ti-edgeai-profile-pipeline` | only if a gate fails |

## Phase 0 - pre-flight
1. **Board SDK -> tools tag**: `ssh root@<board-ip> 'env | grep -i -E "EDGEAI|SDK"'`, then your SoC's column in
   `ti-edgeai-dev/references/sdk-versions.md` / TI's compatibility table (example: TDA4VM on SDK 11.0 -> `11_00_06_00`).
2. **Container** (once, ~10 min): `docker build -f scripts/Dockerfile.tidl-tools --build-arg TIDL_TAG=<tag> --build-arg SOC=<tools soc> -t ti-tidl-tools:<tag>-<soc> scripts/`.
   `run_in_container.sh` finds it through `TIDL_TAG` / `TOOLS_SOC` (defaults: `11_00_06_00`, `am68pa`).
3. Ask before changing the board's system state (services, firmware, folders you did not create). Copying a new model folder is fine.

## Phase 1 - TIDL-friendly ONNX
```bash
python scripts/check_onnx_for_tidl.py model.onnx          # static shapes? unsupported ops? mid-graph Cast? SiLU?
```
- Fix ERRORs (dynamic shapes -> export fixed or run `onnxsim`). Read WARNINGs: ops listed there run on ARM.
- **Input convention**: the board feeds uint8 frames. If your model normalises float input (`(x-mean)*scale`), fold it in:
  `python3 scripts/add_input_preprocessing.py in.onnx out.onnx --mean ... --scale ...` (container; TI's own helper). Models that
  already start with a uint8 -> Cast, or need no normalisation, skip this.
- Detectors: the ONNX should expose the raw head tensors that a TIDL meta-architecture file names. `scripts/export_yolox_tidl_det.py`
  does this for YOLOX (worked adapter: `references/export-yolox-det.md`); other families: `references/other-model-families.md`.
- Prove the ONNX itself is right (framework output == ONNX output) before quantizing anything.

## Phase 2 - compile (container, minutes to ~40 min depending on model and frame count)
```bash
cd work                                   # holds the ONNX (+ prototxt); mounted at the same path in the container
export WORKDIR=$PWD
<skill>/scripts/run_in_container.sh "python3 -m onnxsim model.onnx model_sim.onnx && python3 \$SCRIPTS/compile_tidl.py \
   --model model_sim.onnx --artifacts artifacts --calib <train_images_dir> --task <detection|classification|segmentation> \
   [--meta model.prototxt --meta-arch-type 6] <preprocess flags> --frames 50"
```
Preprocess flags must mirror deployment: `--hw H W` (plain resize; detection/segmentation default) or `--resize S --crop C`
(classification), `--channels bgr|rgb` (what the model expects). Calibration images: training distribution only, >= 50 for
`accuracy_level 1`. The compile writes into a staging folder and only replaces `--artifacts` on success; an existing folder is kept
as `artifacts.previous-<time>` and a failed compile leaves it untouched. Run detached and poll `calib i / N`. Options, failure modes: `references/compile-tidl.md`.

## Phase 3 - verify
```bash
python scripts/check_artifacts_version.py artifacts/subgraph_0_tidl_net.bin --board root@<board-ip>      # stamp
# accuracy in host emulation (container). Float reference first, then int8; same preprocess flags as compile:
python3 $SCRIPTS/eval_onnx_det.py --model model_sim.onnx --data-dir <coco_dir> --split val --hw H W [--tidl-artifacts artifacts --tidl-tools $TIDL_TOOLS_PATH]
python3 $SCRIPTS/eval_classification.py --model model_sim.onnx --images <val_dir> <preprocess flags> --tidl-artifacts artifacts --reference-onnx model_sim.onnx
```
Compare int8 against float on held-out data (and a separate test set when you have one). Typical int8 loss (measured on TDA4VM): small for
classifiers, a few AP points for detectors; if unacceptable go to Phase 6. `eval_classification.py` also works unlabelled:
top-1 agreement and cosine similarity vs float are a label-free measure of quantization damage for any classifier.

## Phase 4/5 - package, deploy, three separate gates
```bash
python scripts/package_model.py --onnx model_sim.onnx --artifacts artifacts --out-dir pkg --name ONR-<TASK>-<nnnn>-<desc> \
   --task <task> [--prototxt model.prototxt] (--hw H W | --resize S --crop C) --channels <bgr|rgb> --classes a b c \
   [--target-device <name>]
BOARD=root@<board-ip> GST_SOC=<key> scripts/deploy_to_board.sh pkg/<name> <finite-input-config.yaml>     # config from ti-edgeai-generate-config
```
`deploy_to_board.sh` never deletes: an existing model/config is refused unless `REPLACE=1`, which moves it to a `.backup-` folder; its
exit status is the application's (finite input must exit 0; live input needs `LIVE=1`). `package_model.py` refuses dynamic input
dimensions, takes detection outputs from the compile metadata, and prints node coverage (a single subgraph is not proof of full
offload; the board log's `Offloaded Nodes N/N` is).

Keep three gates separate; each answers a different question and none implies the others:
1. **Runtime equivalence** (`scripts/board_host_check.py` dump on host and on board, then `compare`): identical input tensors, same
   image list, same outputs/shapes/dtypes, finite values, default tolerance 0 (exact). TI states host emulation should bit-match the
   device; bit-identical outputs were observed for a detector and a classifier on TDA4VM. If it differs, use `debug_level 3` traces.
2. **Application correctness** (`deploy_to_board.sh` + a config from `ti-edgeai-generate-config`): the gst preprocessing
   (`tiovxmultiscaler`, `tiovxdlpreproc`) differs from OpenCV, so do not expect bit-exact results versus gate 1 (TI cautions about this).
   Look at an output frame (detector) or the printed classes (classifier).
3. **Task accuracy** (Phase 3 evaluators on held-out data): float vs int8 vs, if possible, the board's own outputs.

## Phase 6 - accuracy or speed not enough
In this order, re-running Phases 2-3 and recording each result: more/better calibration frames and `accuracy_level 1` ->
16-bit for the first/last convs -> `mixed_precision_factor` -> all 16-bit -> QAT retraining; on SoCs with asymmetric support also try
`--quant-scale-type 4` (not available on TDA4VM). For speed: smaller input,
then `ti-edgeai-profile-pipeline`.

## Report format (always end with this)
```
Model <name> task <task> input <shape/dtype> SoC <S> tools tag <X> board SDK <Y>
Float metric <...>   int8 host-emu metric <...>   held-out int8 <...>
Offload: <n> subgraph(s), Offloaded Nodes N/N | version stamp OK | board==host max|diff| <v> on <k> images
Board model time (bench_tidl.py): <ms>     Run: <list>     Not run: <list>
```
Say exactly what was and was not run.

## Files
`scripts/`: `check_onnx_for_tidl.py`, `add_input_preprocessing.py`, `compile_tidl.py`, `tidl_preprocess.py` (shared preprocessing),
`eval_onnx_det.py`, `eval_classification.py`, `check_artifacts_version.py`, `package_model.py`, `deploy_to_board.sh`,
`board_host_check.py`, `model_manifest.py`, `staged_output.py`, `export_yolox_tidl_det.py` (YOLOX adapter), `run_in_container.sh`, `Dockerfile.tidl-tools`.
`references/`: `export-onnx-for-tidl.md`, `export-yolox-det.md`, `compile-tidl.md`, `quantization-accuracy.md`,
`package-and-deploy.md`, `other-model-families.md`, `model-manifest.md`.
